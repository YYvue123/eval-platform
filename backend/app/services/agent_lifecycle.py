"""Stage-aware collaboration and task tracking, without writing scheduler or scoring facts."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from sqlalchemy import select, func

from app.models import AgentDelegation, AgentEvent, AgentMessage, AgentRun, AgentSession, EvalTask, TaskEvent
from app.utils.jsonutil import dumps, loads


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def stages_for(spec):
    return (spec.get("evaluation_spec") or {}).get("stages") or ["planning"]


async def bind_scenario_roles(db, actor, requirement, bound):
    from app.services.agent_capabilities import list_catalog
    catalog = await list_catalog(db, actor)
    roles = list(bound.get("subagent_roles") or [])
    reasons = []
    for spec in catalog["subagents"]:
        keywords = (spec.get("evaluation_spec") or {}).get("trigger_keywords") or []
        if spec.get("enabled", True) and keywords and any(str(word).lower() in requirement.lower() for word in keywords):
            if spec["role"] not in roles:
                roles.append(spec["role"])
                reasons.append({"role": spec["role"], "reason": "需求匹配已配置场景关键词", "keywords": keywords})
    # Two built-in planning specialists are part of an actual model-generated plan.
    for role in ["plan_analyst", "param_advisor", "report_reviewer"]:
        spec = next((item for item in catalog["subagents"] if item["role"] == role), None)
        if spec and spec.get("enabled", True) and role not in roles:
            roles.append(role)
    return {**bound, "subagent_roles": roles, "auto_selected_roles": reasons}


async def run_stage(db, run, stage, signature, instruction, *, only_role=None):
    from app.services.agent_capabilities import list_catalog, run_subagent
    from app.services.agent_runtime import runtime_actor, append_event
    from app.services.redaction import safe_error_message

    session = await db.get(AgentSession, run.session_id)
    actor = await runtime_actor(db, run)
    plan = loads(session.plan_json, {})
    roles = set((plan.get("capabilities") or {}).get("subagent_roles") or ["monitor", "diagnose"])
    catalog = await list_catalog(db, actor)
    outputs = []
    for spec in catalog["subagents"]:
        if only_role and spec["role"] != only_role:
            continue
        if spec["role"] not in roles or not spec.get("enabled", True) or stage not in stages_for(spec):
            continue
        key = digest([run.id, stage, signature, spec["role"]])
        previous = await db.scalar(select(AgentDelegation).where(
            AgentDelegation.run_id == run.id, AgentDelegation.context_hash == key,
        ).limit(1))
        if previous:
            outputs.append({"role": previous.role, "status": previous.status, "result": loads(previous.result_json, {})})
            continue
        try:
            output = await run_subagent(db, session, actor, spec["role"], instruction=instruction, context_key=key)
            outputs.append(output)
            if spec["role"] == "report_optimizer" and (output.get("result") or {}).get("status") == "analyzed":
                from app.services.agent_report import create_revision
                revision = await create_revision(db, session, run, output, actor)
                await append_event(db, run, "report.optimized", {"revision_id": revision.id, "status": revision.status})
        except PermissionError:
            raise
        except Exception as exc:
            error = safe_error_message(exc)[:400]
            outputs.append({"role": spec["role"], "status": "failed", "error": error})
            await append_event(db, run, "collaboration.failed", {"role": spec["role"], "stage": stage, "error": error})
    return outputs


async def prepare_plan(db, run, cp):
    from app.services.agent_context import resource_inventory
    from app.services.agent_runtime import runtime_actor, append_event

    actor = await runtime_actor(db, run)
    if "resource_inventory" not in cp:
        inventory = await resource_inventory(db, actor, limit=24)
        cp["resource_inventory"] = inventory
        await append_event(db, run, "resources.discovered", inventory)
    from app.services.agent_capabilities import list_catalog
    session = await db.get(AgentSession, run.session_id)
    bound = (loads(session.plan_json, {}).get("capabilities") or {}).get("subagent_roles") or []
    catalog = await list_catalog(db, actor)
    roles = [spec["role"] for spec in catalog["subagents"] if spec["role"] in bound and spec.get("enabled", True) and "planning" in stages_for(spec)]
    completed = list(cp.get("prepared_roles") or [])
    pending = [role for role in roles if role not in completed]
    if pending:
        role = pending[0]
        await run_stage(db, run, "planning", "initial", "规划前检查：依据平台授权资源清单和用户目标，比较候选资源，核对版本、质检、连接、裁判、预算和风险；给主Agent建议，不要创建任务。", only_role=role)
        if loads(run.checkpoint_json, {}).get("tokens_usage_unknown"):
            cp["tokens_usage_unknown"] = True
        cp["prepared_roles"] = completed + [role]
        if len(pending) > 1:
            run.checkpoint_json = dumps(cp)
            return
    rows = (await db.execute(select(AgentDelegation).where(AgentDelegation.run_id == run.id))).scalars().all()
    cp["messages"] = cp.get("messages", []) + [{"role": "user", "content":
        "规划前资源检查与子Agent分析已完成。以下是各角色实际结果，请结合资源清单选择真实资源并形成计划摘要，不要重复空调用任务执行后的角色：" +
        dumps([{ "role": item.role, "status": item.status, "result": loads(item.result_json, {})} for item in rows])}]
    cp["phase"] = "select_tool"
    if loads(run.checkpoint_json, {}).get("tokens_usage_unknown"):
        cp["tokens_usage_unknown"] = True
    run.checkpoint_json = dumps(cp)


async def task_snapshot(db, run):
    session = await db.get(AgentSession, run.session_id)
    task = await db.get(EvalTask, session.task_id) if session.task_id else None
    if task is None:
        return None
    return {"task_id": task.id, "status": task.status, "progress": task.progress, "total": task.total,
            "success_count": task.success_count, "fail_count": task.fail_count, "tokens_used": task.tokens_used,
            "report_available": bool(task.report_path), "task_event_id": await db.scalar(select(func.max(TaskEvent.id)).where(TaskEvent.task_id == task.id)) or 0}


async def snapshot_changed(db, run):
    snapshot = await task_snapshot(db, run)
    if not snapshot:
        return True
    previous = await db.scalar(select(AgentEvent).where(AgentEvent.run_id == run.id, AgentEvent.type.in_(["task.observed", "task.heartbeat"]))
                               .order_by(AgentEvent.id.desc()).limit(1))
    if previous is None:
        return True
    prior = loads(previous.payload_json, {})
    return (any(snapshot.get(key) != prior.get(key) for key in ("status", "fail_count", "report_available"))
            or int(snapshot.get("progress") or 0) // 10 != int(prior.get("progress") or 0) // 10
            or datetime.utcnow() - previous.created_at >= timedelta(minutes=5))


async def track_task(db, run):
    from app.services.agent_runtime import append_event

    snapshot = await task_snapshot(db, run)
    if not snapshot:
        return
    signature = digest(snapshot)
    if await snapshot_changed(db, run):
        previous = await db.scalar(select(AgentEvent).where(AgentEvent.run_id == run.id, AgentEvent.type.in_(["task.observed", "task.heartbeat"])).order_by(AgentEvent.id.desc()).limit(1))
        heartbeat = previous is not None and loads(previous.payload_json, {}).get("signature") == signature
        await append_event(db, run, "task.heartbeat" if heartbeat else "task.observed", {**snapshot, "signature": signature})
        db.add(AgentMessage(session_id=run.session_id, role="system", tool_name="task_tracking",
                            content=("任务仍在执行（定时跟进，未检测到新的进度变化）。" if heartbeat else "任务状态更新。") + f"任务 #{snapshot['task_id']}：{snapshot['status']}，进度{snapshot['progress']}%，通过{snapshot['success_count']}、失败{snapshot['fail_count']}。",
                            payload_json=dumps({"run_id": run.id, **snapshot})))
        await run_stage(db, run, "monitoring", signature, "根据本次实际任务快照和逐样本证据报告状态、变化和风险；不要猜测结果或自行恢复。")
    if snapshot["status"] in {"failed", "partial_failed", "paused_budget"} or (snapshot["status"] == "success" and snapshot["fail_count"]):
        await run_stage(db, run, "diagnosis", signature, "对本任务实际失败样本、事件和错误进行归因，给出需要人工确认的验证与补测建议。")
    if snapshot["status"] in {"success", "failed", "partial_failed", "cancelled", "paused_budget"}:
        await run_stage(db, run, "review", signature, "任务已结束，请核对任务统计、样本结果和报告口径，指出不确定性与证据缺口。")
        if snapshot["report_available"]:
            await run_stage(db, run, "optimization", signature, "请基于真实样本与报告，输出清晰、完整、有证据引用的中文Markdown优化报告；不修改原分数或结果，供人员审核。")


async def ensure_followup(db, session):
    from app.services.agent_runtime import create_run, append_event

    if not session.planner_model_id:
        return None
    if session.active_run_id:
        active = await db.get(AgentRun, session.active_run_id)
        if active and active.status in {"queued", "running", "waiting"}:
            plan = loads(session.plan_json, {})
            cp = loads(active.checkpoint_json, {})
            from app.services.goal_spec import canonical_plan_hash
            if active.status in {"queued", "waiting"} and cp.get("phase") == "await_approval" and cp.get("approval_plan_hash") != canonical_plan_hash(plan):
                from datetime import datetime
                active.status = "cancelled"
                active.finished_at = datetime.utcnow()
                active.lease_owner = ""
                active.lease_until = None
                await append_event(db, active, "run.cancelled", {"reason": "approved_plan_changed", "message": "原审批等待轮对应旧计划，已保留历史并改由新跟踪轮处理当前已确认任务。"})
                session.active_run_id = None
            else:
                plan["tracking_run_id"] = active.id
                session.plan_json = dumps(plan)
                return active
    plan = loads(session.plan_json, {})
    run = await create_run(db, session, message=f"跟进已确认任务 #{session.task_id} 的执行状态、异常、报告与专项角色协作。", purpose="followup",
                           max_rounds=8, token_budget=int(plan.get("token_budget") or 0))
    await append_event(db, run, "task.tracking_started", {"task_id": session.task_id})
    return run
