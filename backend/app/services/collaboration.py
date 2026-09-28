"""专项协作：按需委派、深度/并行上限、监控去重、诊断证据、恢复升级。"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AgentDelegation,
    AgentMessage,
    AgentMonitorState,
    AgentSession,
    AgentSuggestion,
    EvalTask,
    TaskEvent,
)
from app.services.agent_tools import diagnose_task, monitor_task
from app.utils.jsonutil import dumps, loads

MAX_DEPTH = 2
MAX_PARALLEL = 2

# 子 Agent 允许的只读工具；禁止任务写工具
SUB_AGENT_TOOLS = frozenset({"monitor_task", "diagnose_task", "search_knowledge", "validate_eval_config"})
FORBIDDEN_WRITE_TOOLS = frozenset({"create_task", "enqueue_task", "cancel_task", "retry_task"})


def assert_sub_agent_tool(tool_name: str) -> None:
    if tool_name in FORBIDDEN_WRITE_TOOLS:
        raise PermissionError(f"sub_agent_forbidden_write:{tool_name}")
    if tool_name and tool_name not in SUB_AGENT_TOOLS:
        raise PermissionError(f"sub_agent_unknown_tool:{tool_name}")


def plan_roles(task: EvalTask | None, *, force: list[str] | None = None) -> list[str]:
    """简单任务只开 monitor；失败/高风险才 diagnose；成功可 review。"""
    if force:
        return list(force)
    if not task:
        return ["monitor"]
    roles = ["monitor"]
    if task.status in {"failed", "partial_failed", "paused_budget"}:
        roles.append("diagnose")
    if task.status == "success" and (task.fail_count or 0) == 0:
        roles.append("review")
    # analysis 仅复杂场景（有依赖或正式非 trial）
    if not task.trial_run and task.status in {"failed", "running"}:
        if "diagnose" not in roles:
            roles.append("diagnose")
    return roles[:MAX_PARALLEL]


def _context_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _summary_hash(report: dict) -> str:
    body = {
        "status": report.get("status"),
        "progress": report.get("progress"),
        "risk": report.get("risk"),
        "success_count": report.get("success_count"),
        "fail_count": report.get("fail_count"),
        "summary": report.get("summary"),
    }
    return _context_hash(body)


def delegation_out(d: AgentDelegation) -> dict:
    return {
        "id": d.id,
        "session_id": d.session_id,
        "run_id": d.run_id,
        "parent_delegation_id": d.parent_delegation_id,
        "role": d.role,
        "depth": d.depth,
        "context_hash": d.context_hash,
        "budget_slice": d.budget_slice,
        "status": d.status,
        "result": loads(d.result_json, {}),
        "evidence": loads(d.evidence_json, []),
        "error_code": d.error_code or "",
        "created_at": d.created_at.isoformat() + "Z" if d.created_at else None,
        "finished_at": d.finished_at.isoformat() + "Z" if d.finished_at else None,
    }


async def _depth_of(db: AsyncSession, parent_id: int | None) -> int:
    if not parent_id:
        return 1
    parent = await db.get(AgentDelegation, parent_id)
    return int(parent.depth if parent else 0) + 1


async def _active_parallel(db: AsyncSession, session_id: int) -> int:
    rows = (
        await db.execute(
            select(AgentDelegation).where(
                AgentDelegation.session_id == session_id,
                AgentDelegation.status == "running",
            )
        )
    ).scalars().all()
    return len(rows)


async def run_collaborators(
    db: AsyncSession,
    session: AgentSession,
    *,
    force_roles: list[str] | None = None,
    parent_delegation_id: int | None = None,
    budget_total: int = 100,
) -> dict:
    if not session.task_id:
        raise HTTPException(400, "会话尚未关联任务，无法委派专项 Agent")
    task = await db.get(EvalTask, session.task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    depth = await _depth_of(db, parent_delegation_id)
    if depth > MAX_DEPTH:
        raise HTTPException(400, f"委派深度超过上限 {MAX_DEPTH}")

    roles = plan_roles(task, force=force_roles)
    # 简单成功且非 force：仅 monitor
    if not force_roles and task.status in {"queued", "draft", "running"} and task.status != "failed":
        if task.status in {"queued", "draft"}:
            roles = ["monitor"]

    running = await _active_parallel(db, session.id)
    slots = max(0, MAX_PARALLEL - running)
    if slots <= 0:
        raise HTTPException(409, f"并行委派已达上限 {MAX_PARALLEL}")

    roles = roles[:slots]
    slice_each = max(1, int(budget_total) // max(1, len(roles))) if roles else 0
    results = []
    for role in roles:
        ctx = {"role": role, "task_id": task.id, "status": task.status, "progress": task.progress}
        ch = _context_hash(ctx)
        # 同 context 防重复委派
        dup = await db.scalar(
            select(AgentDelegation).where(
                AgentDelegation.session_id == session.id,
                AgentDelegation.role == role,
                AgentDelegation.context_hash == ch,
                AgentDelegation.status.in_(["running", "success"]),
            )
        )
        if dup:
            results.append({**delegation_out(dup), "deduped": True})
            continue

        d = AgentDelegation(
            session_id=session.id,
            run_id=session.active_run_id,
            parent_delegation_id=parent_delegation_id,
            role=role,
            depth=depth,
            context_hash=ch,
            budget_slice=slice_each,
            status="running",
            tenant_id=session.tenant_id,
        )
        db.add(d)
        await db.flush()

        try:
            if role == "monitor":
                out = await _run_monitor(db, session, task, d)
            elif role == "diagnose":
                out = await _run_diagnose(db, session, task, d)
            elif role == "review":
                out = await _run_review(db, session, task, d)
            else:
                out = {"ok": True, "note": "analysis deferred", "skipped": True}
                d.status = "skipped"
            d.result_json = dumps(out)
            if d.status == "running":
                d.status = "success"
            d.finished_at = datetime.utcnow()
        except Exception as exc:  # noqa: BLE001
            d.status = "failed"
            d.error_code = "role_failed"
            d.result_json = dumps({"ok": False, "error": str(exc)})
            d.finished_at = datetime.utcnow()
        await db.flush()
        results.append(delegation_out(d))

    return {"roles": roles, "items": results, "max_depth": MAX_DEPTH, "max_parallel": MAX_PARALLEL}


async def _run_monitor(db: AsyncSession, session: AgentSession, task: EvalTask, d: AgentDelegation) -> dict:
    assert_sub_agent_tool("monitor_task")
    report = await monitor_task(db, task.id)
    sh = _summary_hash(report)
    state = await db.scalar(select(AgentMonitorState).where(AgentMonitorState.task_id == task.id))
    skipped_llm = False
    if state and state.last_summary_hash == sh:
        skipped_llm = True
        report = {**report, "unchanged": True, "skipped_llm": True}
        d.status = "skipped"
    else:
        if not state:
            state = AgentMonitorState(task_id=task.id, tenant_id=session.tenant_id)
            db.add(state)
        state.session_id = session.id
        state.run_id = session.active_run_id
        state.last_summary_hash = sh
        state.risk_level = report.get("risk") or "low"
        state.last_llm_at = datetime.utcnow()
        state.updated_at = datetime.utcnow()
        evs = (await db.execute(select(TaskEvent).where(TaskEvent.task_id == task.id).order_by(TaskEvent.id.desc()).limit(1))).scalars().all()
        state.last_event_seq = evs[0].id if evs else 0

    evidence = [
        {"type": "task_status", "ref": f"task:{task.id}", "value": task.status},
        {"type": "progress", "ref": f"task:{task.id}:progress", "value": task.progress},
        {"type": "summary_hash", "ref": sh, "value": report.get("summary")},
    ]
    d.evidence_json = dumps(evidence)
    db.add(AgentMessage(session_id=session.id, role="monitor", content=report.get("summary") or "", tool_name="monitor_task", payload_json=dumps(report)))
    return {**report, "skipped_llm": skipped_llm, "evidence": evidence}


async def _run_diagnose(db: AsyncSession, session: AgentSession, task: EvalTask, d: AgentDelegation) -> dict:
    assert_sub_agent_tool("diagnose_task")
    result = await diagnose_task(db, task.id)
    evidence = [
        {"type": "task_error", "ref": f"task:{task.id}:error", "value": task.error_message or ""},
        {"type": "fail_count", "ref": f"task:{task.id}:fail", "value": task.fail_count},
        {"type": "status", "ref": f"task:{task.id}:status", "value": task.status},
    ]
    verification = [
        {"step": "check_dataset_quality", "required": True},
        {"step": "check_model_health", "required": True},
        {"step": "human_confirm_before_retry", "required": True},
    ]
    # 相同恢复失败升级人工
    prior = (
        await db.execute(
            select(AgentDelegation).where(
                AgentDelegation.session_id == session.id,
                AgentDelegation.role == "diagnose",
                AgentDelegation.status == "escalated",
            )
        )
    ).scalars().all()
    fail_retries = [
        s for s in (result.get("suggestions") or []) if s.get("action") == "retry"
    ]
    if prior and fail_retries:
        result["escalated"] = True
        result["escalation"] = "identical_recovery_failed_escalate_human"
        d.status = "escalated"
        d.error_code = "escalate_human"
    elif task.status == "failed":
        # 首次失败记建议，需主 Agent 审批才能恢复
        for item in result.get("suggestions") or []:
            if item.get("action") == "retry":
                db.add(
                    AgentSuggestion(
                        session_id=session.id,
                        task_id=task.id,
                        action=item["action"],
                        reason=item["reason"] + "（须主审批后执行）",
                    )
                )

    result["evidence"] = evidence
    result["verification_steps"] = verification
    result["requires_main_approval"] = True
    d.evidence_json = dumps(evidence)
    db.add(
        AgentMessage(
            session_id=session.id,
            role="diagnose",
            content="诊断完成，恢复须主 Agent 审批；子 Agent 无任务写工具。",
            tool_name="diagnose_task",
            payload_json=dumps(result),
        )
    )
    return result


async def _run_review(db: AsyncSession, session: AgentSession, task: EvalTask, d: AgentDelegation) -> dict:
    evidence = [
        {"type": "pass_rate", "ref": f"task:{task.id}:pass_rate", "value": task.pass_rate},
        {"type": "avg_score", "ref": f"task:{task.id}:avg_score", "value": task.avg_score},
        {"type": "report", "ref": f"task:{task.id}:report", "value": (task.report_summary or "")[:200]},
    ]
    d.evidence_json = dumps(evidence)
    out = {
        "ok": True,
        "task_id": task.id,
        "verdict": "ready_to_archive" if task.status == "success" else "keep_watching",
        "evidence": evidence,
        "citation_valid": bool(task.id),
    }
    db.add(AgentMessage(session_id=session.id, role="main", content=f"review: {out['verdict']}", tool_name="review_task", payload_json=dumps(out)))
    return out


async def list_delegations(db: AsyncSession, session_id: int) -> list[AgentDelegation]:
    return list(
        (
            await db.execute(
                select(AgentDelegation).where(AgentDelegation.session_id == session_id).order_by(AgentDelegation.id.desc())
            )
        ).scalars().all()
    )
