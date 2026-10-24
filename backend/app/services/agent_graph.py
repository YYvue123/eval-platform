"""LangGraph owns routing and durable execution. Platform services own business facts."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TypedDict

from fastapi import HTTPException
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import select, func, update

from app.models import AgentApproval, AgentMessage, AgentRun, AgentSession, EvalTask, EvalResult
from app.services.agent_checkpointer import AgentCheckpointer
from app.utils.jsonutil import dumps, loads


class RuntimeState(TypedDict):
    checkpoint: dict


async def task_completion(db, run) -> dict:
    from app.services.agent_runtime import runtime_actor
    from app.services.object_policy import object_is_visible

    actor = await runtime_actor(db, run)
    session = await db.get(AgentSession, run.session_id)
    if not session.task_id:
        return {"kind": "conversation_completed", "objective_verified": False, "reason": "no_evaluation_task"}
    task = await db.get(EvalTask, session.task_id)
    if not object_is_visible(task, actor):
        raise ValueError("task_not_visible")
    status = task.status
    measured = int(await db.scalar(select(func.count(EvalResult.id)).where(
        EvalResult.task_id == task.id, EvalResult.execution_status == "ok",
        EvalResult.score_status == "scored", EvalResult.simulation.is_(False),
    )) or 0)
    verified = (
        status == "success" and bool((task.report_path or "").strip())
        and not task.trial_run and not task.simulation and int(task.total or 0) > 0
        and measured == int(task.total)
    )
    terminal = status in {"success", "failed", "partial_failed", "cancelled", "paused_budget"}
    return {
        "kind": "evaluation_completed" if verified else "evaluation_unverified" if terminal else "task_pending",
        "objective_verified": verified,
        "verification_scope": "evaluation_execution",
        "measured_results": measured,
        "task_id": task.id,
        "task_status": status,
        "report_available": bool((task.report_path or "").strip()),
        "trial_run": bool(task.trial_run),
        "success_count": task.success_count or 0,
        "fail_count": task.fail_count or 0,
    }


async def _approval_consumed(db, run, cp):
    from app.services.goal_spec import canonical_plan_hash

    session = await db.get(AgentSession, run.session_id)
    expected = cp.get("approval_plan_hash")
    if not session or not session.task_id or expected != canonical_plan_hash(loads(session.plan_json, {})):
        return False
    return bool(await db.scalar(select(AgentApproval.id).where(
        AgentApproval.session_id == session.id,
        AgentApproval.tenant_id == session.tenant_id,
        AgentApproval.plan_hash == expected,
        AgentApproval.status == "consumed",
        AgentApproval.consumed_task_id == session.task_id,
    ).limit(1)))


async def can_resume(db, run):
    cp = loads(run.checkpoint_json, {})
    if cp.get("phase") == "await_approval" and run.status == "waiting":
        return await _approval_consumed(db, run, cp)
    if cp.get("phase") == "verify" and run.status == "waiting":
        from app.services.agent_lifecycle import snapshot_changed
        return await snapshot_changed(db, run)
    return True


async def _await_approval(db, run, cp):
    from app.services.agent_runtime import append_event

    if not await _approval_consumed(db, run, cp):
        run.status = "waiting"
        run.checkpoint_json = dumps(cp)
        await append_event(db, run, "run.waiting_approval", {"plan_hash": cp.get("approval_plan_hash")})
        interrupt({"kind": "approval_required", "session_id": run.session_id, "plan_hash": cp.get("approval_plan_hash")})
    # Command(resume=...) alone cannot authorize execution: always check the DB.
    if not await _approval_consumed(db, run, cp):
        raise ValueError("approval_required")
    run.status = "running"
    cp["phase"] = "verify"
    run.checkpoint_json = dumps(cp)


async def _verify(db, run, cp):
    from app.services.agent_runtime import _clear_active, append_event
    from app.services.agent_lifecycle import track_task

    session = await db.get(AgentSession, run.session_id)
    tracking = loads(session.plan_json, {}).get("tracking_run_id") == run.id
    if cp.get("purpose") == "followup" or cp.get("approval_plan_hash") or tracking:
        await track_task(db, run)
        if loads(run.checkpoint_json, {}).get("tokens_usage_unknown"):
            cp["tokens_usage_unknown"] = True
    completion = await task_completion(db, run)
    cp["completion"] = completion
    if completion["kind"] == "task_pending":
        run.status = "waiting"
        run.checkpoint_json = dumps(cp)
        await append_event(db, run, "run.waiting_task", completion)
        # A progress update can resume this node while the task is still running.
        # Consume earlier resume values and suspend again until facts are terminal.
        while completion["kind"] == "task_pending":
            interrupt(completion)
    terminal_error = completion.get("task_status") in {"failed", "partial_failed", "cancelled", "paused_budget"}
    run.status = "failed" if terminal_error else "success"
    if terminal_error:
        run.error_code = "evaluation_task_failed"
        run.error_message = f"任务状态：{completion['task_status']}"
    cp["phase"] = "done"
    reply = cp.get("final_reply") or (
        f"评测任务 #{completion.get('task_id')} 状态：{completion.get('task_status')}；"
        f"目标核验：{'通过' if completion['objective_verified'] else '未通过'}。"
    )
    if completion.get("task_id"):
        # The fact-based suffix cannot be replaced by a model's completion claim.
        reply += f"\n实际任务状态：{completion['task_status']}；目标核验：{'通过' if completion['objective_verified'] else '未通过'}。"
        from app.models import AgentDelegation, AgentReportRevision
        rows = (await db.execute(select(AgentDelegation).where(AgentDelegation.run_id == run.id)
                                 .order_by(AgentDelegation.id))).scalars().all()
        latest = {row.role: row for row in rows}
        for role, row in latest.items():
            result = loads(row.result_json, {})
            reply += f"\n\n{role}（记录 #{row.id}，{row.status}）：" + str(result.get("summary") or row.error_code or "无可用分析")[:900]
        revisions = (await db.execute(select(AgentReportRevision).where(AgentReportRevision.run_id == run.id))).scalars().all()
        if revisions:
            reply += "\n\n优化报告已另存为待人工审核版本：" + "、".join(f"#{row.id}" for row in revisions) + "。原始报告与评分保留。"
    cp["final_reply"] = reply
    run.checkpoint_json = dumps(cp)
    run.finished_at = datetime.utcnow()
    run.lease_owner = ""
    run.lease_until = None
    db.add(AgentMessage(session_id=run.session_id, role="main", content=reply, tool_name="agent_runtime", payload_json=dumps({"run_id": run.id, "purpose": cp.get("purpose", "dialogue")})))
    await append_event(db, run, "run.verified", completion)
    await append_event(db, run, "run.failed" if terminal_error else "run.success", {"completion": completion})
    await _clear_active(db, run)


def build_graph(db, run, saver, fencing_token=None):
    from app.services import agent_runtime as runtime

    handlers = {
        "select_tool": runtime._select_tool_node,
        "observe": runtime._observe_node,
        "reply": runtime._reply_node,
        "await_approval": _await_approval,
        "verify": _verify,
    }
    from app.services.agent_lifecycle import prepare_plan
    handlers["prepare"] = prepare_plan

    def node(handler):
        async def invoke(state):
            async with saver.lock:
                if fencing_token is not None and int(run.fencing_token or 0) != int(fencing_token):
                    raise HTTPException(409, "fencing_token 不匹配")
                if fencing_token is not None:
                    # Lock the owned run in this transaction before any model/tool call.
                    # Checking the ORM instance alone misses a replacement worker's token.
                    held = await db.execute(update(AgentRun).where(
                        AgentRun.id == run.id, AgentRun.fencing_token == fencing_token,
                        AgentRun.status == "running",
                    ).values(lease_until=datetime.utcnow() + timedelta(seconds=runtime.LEASE_SECONDS))
                        .execution_options(synchronize_session=False))
                    if held.rowcount != 1:
                        raise HTTPException(409, "fencing_token 不匹配或 run 已结束")
                cp = state["checkpoint"]
                if run.cancel_requested:
                    run.status = "cancelled"
                    run.finished_at = datetime.utcnow()
                    await runtime.append_event(db, run, "run.cancelled", {})
                    await runtime._clear_active(db, run)
                else:
                    await runtime.runtime_actor(db, run)
                    await handler(db, run, cp)
                run.checkpoint_json = dumps(cp)
                await db.flush()
                return {"checkpoint": cp}
        return invoke

    def route(state):
        if run.status not in {"running", "queued"}:
            return END
        phase = state["checkpoint"].get("phase", "select_tool")
        if phase == "done":
            return END
        if phase not in handlers:
            raise ValueError(f"unknown_phase:{phase}")
        return phase

    graph = StateGraph(RuntimeState)
    graph.add_conditional_edges(START, route)
    for name, handler in handlers.items():
        graph.add_node(name, node(handler))
        graph.add_conditional_edges(name, route)
    return graph.compile(checkpointer=saver, name="evaluation_coordinator")


async def advance_graph(db, run, *, fencing_token=None):
    from app.services import agent_runtime as runtime

    if fencing_token is not None and int(run.fencing_token or 0) != int(fencing_token):
        raise HTTPException(409, "fencing_token 不匹配")
    saver = AgentCheckpointer(db, run)
    graph = build_graph(db, run, saver, fencing_token)
    config = {"configurable": {"thread_id": run.checkpoint_thread_id}}
    try:
        saved = await graph.aget_state(config)
        cp = loads(run.checkpoint_json, {})
        if not saved.values:
            value = {"checkpoint": cp}  # Also imports legacy runtime-v1 checkpoints.
        elif any(task.interrupts for task in saved.tasks):
            if not await can_resume(db, run):
                run.status = "waiting"
                return run
            value = Command(resume={"continue": True})
        elif saved.next:
            value = None
        else:
            # Retry a failed node using the durable projection, without replaying completed tools.
            value = {"checkpoint": cp}
        run.graph_version = runtime.GRAPH_VERSION
        await graph.ainvoke(value, config, interrupt_after=["prepare", "select_tool", "observe", "reply", "await_approval", "verify"], durability="sync")
        if run.status == "running":
            run.lease_until = datetime.utcnow() + timedelta(seconds=runtime.LEASE_SECONDS)
    except Exception as exc:
        if isinstance(exc, HTTPException) and exc.status_code == 409:
            raise
        from app.services.redaction import safe_error_message

        run.status = "paused_budget" if isinstance(exc, PermissionError) else "failed"
        run.error_code = "budget_exceeded" if isinstance(exc, PermissionError) else "runtime_error"
        run.error_message = safe_error_message(exc)[:300]
        if cp.get("purpose") == "planning":
            session = await db.get(AgentSession, run.session_id)
            plan = loads(session.plan_json, {})
            plan["analysis_status"] = "failed"
            session.plan_json = dumps(plan)
        run.finished_at = datetime.utcnow()
        await runtime.append_event(db, run, "run.failed", {"error_code": run.error_code})
        await runtime._clear_active(db, run)
    await db.flush()
    return run
