"""轻量持久化 Agent 运行时：工具循环、checkpoint、lease/fencing、事件序。"""
from __future__ import annotations

import os
import socket
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentEvent, AgentRun, AgentSession, AgentMessage
from app.utils.jsonutil import dumps, loads

LEASE_SECONDS = 60
GRAPH_VERSION = "runtime-v1"

# 允许调用的工具：名称 → JSON Schema（parameters）
TOOL_SCHEMAS: dict[str, dict] = {
    "search_knowledge": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    },
    "infer_dims": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    },
}


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _validate_tool_args(name: str, args: Any) -> None:
    if name not in TOOL_SCHEMAS:
        raise ValueError(f"unknown_tool:{name}")
    schema = TOOL_SCHEMAS[name]
    if not isinstance(args, dict):
        raise ValueError(f"invalid_tool_args:{name}")
    required = schema.get("required") or []
    for key in required:
        if key not in args:
            raise ValueError(f"invalid_tool_schema:{name}:missing:{key}")
    if schema.get("additionalProperties") is False:
        allowed = set((schema.get("properties") or {}).keys())
        extra = set(args.keys()) - allowed
        if extra:
            raise ValueError(f"invalid_tool_schema:{name}:extra:{sorted(extra)}")
    for key, val in args.items():
        prop = (schema.get("properties") or {}).get(key) or {}
        if prop.get("type") == "string" and not isinstance(val, str):
            raise ValueError(f"invalid_tool_schema:{name}:type:{key}")


async def append_event(
    db: AsyncSession,
    run: AgentRun,
    event_type: str,
    payload: dict | None = None,
    *,
    step_id: str = "",
) -> AgentEvent:
    run.event_seq = int(run.event_seq or 0) + 1
    ev = AgentEvent(
        run_id=run.id,
        seq=run.event_seq,
        type=event_type,
        step_id=step_id,
        payload_json=dumps(payload or {}),
    )
    db.add(ev)
    run.updated_at = datetime.utcnow()
    await db.flush()
    return ev


def run_out(run: AgentRun) -> dict:
    return {
        "id": run.id,
        "session_id": run.session_id,
        "status": run.status,
        "provider": run.provider,
        "graph_version": run.graph_version,
        "checkpoint": loads(run.checkpoint_json, {}),
        "checkpoint_thread_id": run.checkpoint_thread_id,
        "lease_owner": run.lease_owner or "",
        "fencing_token": run.fencing_token or 0,
        "cancel_requested": bool(run.cancel_requested),
        "max_rounds": run.max_rounds,
        "rounds_used": run.rounds_used,
        "token_budget": run.token_budget,
        "tokens_used": run.tokens_used,
        "error_code": run.error_code or "",
        "error_message": run.error_message or "",
        "event_seq": run.event_seq,
        "created_at": run.created_at.isoformat() + "Z" if run.created_at else None,
        "finished_at": run.finished_at.isoformat() + "Z" if run.finished_at else None,
    }


def event_out(ev: AgentEvent) -> dict:
    return {
        "id": ev.id,
        "run_id": ev.run_id,
        "seq": ev.seq,
        "type": ev.type,
        "step_id": ev.step_id,
        "payload": loads(ev.payload_json, {}),
        "created_at": ev.created_at.isoformat() + "Z" if ev.created_at else None,
    }


def _default_checkpoint(user_message: str) -> dict:
    return {
        "schema_version": 1,
        "phase": "select_tool",  # select_tool | observe | reply | done
        "messages": [{"role": "user", "content": user_message}],
        "pending_tool": None,
        "observations": [],
        "final_reply": "",
    }


async def create_run(
    db: AsyncSession,
    session: AgentSession,
    *,
    message: str,
    provider: str = "mock",
    max_rounds: int = 8,
    token_budget: int = 0,
    client_message_id: str = "",
) -> AgentRun:
    """创建 run；若已有 active run 则 409。"""
    if session.active_run_id:
        active = await db.get(AgentRun, session.active_run_id)
        if active and active.status in {"queued", "running", "waiting"}:
            raise HTTPException(409, "会话已有活跃 run，禁止并发启动")

    if provider not in {"mock", "live"}:
        raise HTTPException(400, "provider 仅支持 mock|live")

    thread = f"sess-{session.id}-{uuid.uuid4().hex[:12]}"
    run = AgentRun(
        session_id=session.id,
        tenant_id=session.tenant_id,
        status="queued",
        graph_version=GRAPH_VERSION,
        provider=provider,
        checkpoint_json=dumps(_default_checkpoint(message)),
        checkpoint_thread_id=thread,
        max_rounds=max(1, int(max_rounds or 8)),
        token_budget=max(0, int(token_budget or 0)),
    )
    db.add(run)
    await db.flush()
    session.active_run_id = run.id
    session.row_version = int(session.row_version or 0) + 1
    session.updated_at = datetime.utcnow()
    db.add(AgentMessage(session_id=session.id, role="user", content=message, tool_name="", payload_json=dumps({"client_message_id": client_message_id})))
    await append_event(db, run, "run.created", {"provider": provider, "message": message[:200]})
    await db.flush()
    return run


async def claim_run(db: AsyncSession, run_id: int, *, owner: str | None = None) -> tuple[AgentRun | None, int]:
    run = await db.get(AgentRun, run_id)
    if not run or run.status not in {"queued", "waiting"}:
        return None, 0
    if run.cancel_requested:
        run.status = "cancelled"
        run.finished_at = datetime.utcnow()
        await append_event(db, run, "run.cancelled", {"phase": "before_claim"})
        await _clear_active(db, run)
        return None, 0
    owner = owner or worker_id()
    token = int(run.fencing_token or 0) + 1
    run.fencing_token = token
    run.lease_owner = owner
    run.lease_until = datetime.utcnow() + timedelta(seconds=LEASE_SECONDS)
    run.status = "running"
    run.row_version = int(run.row_version or 0) + 1
    await append_event(db, run, "run.claimed", {"owner": owner, "fencing_token": token})
    await db.flush()
    return run, token


async def _clear_active(db: AsyncSession, run: AgentRun) -> None:
    session = await db.get(AgentSession, run.session_id)
    if session and session.active_run_id == run.id:
        session.active_run_id = None
        session.row_version = int(session.row_version or 0) + 1


async def request_cancel(db: AsyncSession, run: AgentRun) -> AgentRun:
    if run.status in {"success", "failed", "cancelled", "paused_budget"}:
        raise HTTPException(400, "run 已结束")
    run.cancel_requested = True
    if run.status in {"queued", "waiting"}:
        run.status = "cancelled"
        run.finished_at = datetime.utcnow()
        run.lease_owner = ""
        run.lease_until = None
        await append_event(db, run, "run.cancelled", {"phase": "queued"})
        await _clear_active(db, run)
    else:
        await append_event(db, run, "run.cancel_requested", {})
    await db.flush()
    return run


def _mock_select_tool(checkpoint: dict) -> dict:
    """确定性：首轮调 search_knowledge，其后回复。"""
    obs = checkpoint.get("observations") or []
    user = ""
    for m in checkpoint.get("messages") or []:
        if m.get("role") == "user":
            user = m.get("content") or ""
            break
    if not obs:
        return {"name": "search_knowledge", "arguments": {"query": (user or "评测")[:40]}}
    return {}


async def _execute_tool(db: AsyncSession, name: str, args: dict) -> dict:
    _validate_tool_args(name, args)
    if name == "search_knowledge":
        from app.services.agent_tools import search_knowledge

        items = await search_knowledge(db, args.get("query") or "")
        return {"items": items[:5], "count": len(items)}
    if name == "infer_dims":
        from app.services.agent_orchestrator import infer_dims

        scene, industry = infer_dims(args.get("text") or "")
        return {"scene": scene, "industry": industry}
    raise ValueError(f"unknown_tool:{name}")


async def _charge_tokens(run: AgentRun, n: int) -> None:
    run.tokens_used = int(run.tokens_used or 0) + max(0, n)
    if run.token_budget and run.tokens_used > run.token_budget:
        raise PermissionError("budget_exceeded")


async def step_once(db: AsyncSession, run: AgentRun, *, fencing_token: int | None = None) -> AgentRun:
    """推进一个阶段并写 checkpoint。"""
    if fencing_token is not None and int(run.fencing_token or 0) != int(fencing_token):
        raise HTTPException(409, "fencing_token 不匹配")
    if run.cancel_requested:
        run.status = "cancelled"
        run.finished_at = datetime.utcnow()
        run.lease_owner = ""
        await append_event(db, run, "run.cancelled", {"phase": "step"})
        await _clear_active(db, run)
        await db.flush()
        return run

    cp = loads(run.checkpoint_json, {})
    phase = cp.get("phase") or "select_tool"

    try:
        if phase == "select_tool":
            run.rounds_used = int(run.rounds_used or 0) + 1
            if run.rounds_used > run.max_rounds:
                run.status = "failed"
                run.error_code = "max_rounds"
                run.error_message = "超过最大轮次"
                run.finished_at = datetime.utcnow()
                await append_event(db, run, "run.failed", {"error_code": "max_rounds"})
                await _clear_active(db, run)
                await db.flush()
                return run

            if run.provider == "mock":
                tool = _mock_select_tool(cp)
            else:
                # live：无真实 tool-calling 时降级为 mock 选择，并记事件
                tool = _mock_select_tool(cp)
                await append_event(db, run, "provider.fallback_mock_select", {})

            await _charge_tokens(run, 10)
            if not tool:
                cp["phase"] = "reply"
                run.checkpoint_json = dumps(cp)
                await append_event(db, run, "llm.select_none", {})
            else:
                try:
                    _validate_tool_args(tool["name"], tool.get("arguments") or {})
                except ValueError as exc:
                    run.status = "failed"
                    run.error_code = "invalid_tool_schema"
                    run.error_message = str(exc)
                    run.finished_at = datetime.utcnow()
                    await append_event(db, run, "tool.rejected", {"error": str(exc), "tool": tool})
                    await _clear_active(db, run)
                    await db.flush()
                    return run
                cp["pending_tool"] = tool
                cp["phase"] = "observe"
                run.checkpoint_json = dumps(cp)
                await append_event(db, run, "tool.selected", {"tool": tool}, step_id=f"r{run.rounds_used}")

        elif phase == "observe":
            tool = cp.get("pending_tool") or {}
            name = tool.get("name") or ""
            args = tool.get("arguments") or {}
            try:
                result = await _execute_tool(db, name, args)
            except ValueError as exc:
                run.status = "failed"
                run.error_code = "tool_failed"
                run.error_message = str(exc)
                run.finished_at = datetime.utcnow()
                await append_event(db, run, "tool.failed", {"error": str(exc), "tool": name})
                await _clear_active(db, run)
                await db.flush()
                return run
            obs = list(cp.get("observations") or [])
            obs.append({"tool": name, "result": result})
            cp["observations"] = obs
            cp["pending_tool"] = None
            cp["phase"] = "select_tool"
            run.checkpoint_json = dumps(cp)
            await append_event(db, run, "tool.observed", {"tool": name, "result": result}, step_id=f"r{run.rounds_used}")

        elif phase == "reply":
            obs = cp.get("observations") or []
            reply = f"已完成工具循环，观察 {len(obs)} 次。"
            if obs:
                first = obs[0].get("result") or {}
                if "count" in first:
                    reply = f"检索到 {first.get('count')} 条知识，可继续确认计划。"
            cp["final_reply"] = reply
            cp["phase"] = "done"
            run.checkpoint_json = dumps(cp)
            await _charge_tokens(run, 5)
            await append_event(db, run, "llm.reply", {"content": reply})
            db.add(AgentMessage(session_id=run.session_id, role="main", content=reply, tool_name="agent_runtime"))
            run.status = "success"
            run.finished_at = datetime.utcnow()
            run.lease_owner = ""
            await append_event(db, run, "run.success", {})
            await _clear_active(db, run)

        else:
            run.status = "success"
            run.finished_at = datetime.utcnow()
            await _clear_active(db, run)

    except PermissionError:
        run.status = "paused_budget"
        run.error_code = "budget_exceeded"
        run.error_message = "token 预算耗尽"
        run.finished_at = datetime.utcnow()
        run.lease_owner = ""
        await append_event(db, run, "run.paused_budget", {"tokens_used": run.tokens_used, "token_budget": run.token_budget})
        await _clear_active(db, run)

    run.lease_until = datetime.utcnow() + timedelta(seconds=LEASE_SECONDS)
    await db.flush()
    return run


async def execute_until_idle(
    db: AsyncSession,
    run_id: int,
    *,
    fencing_token: int | None = None,
    max_steps: int = 32,
) -> AgentRun:
    run = await db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(404, "run 不存在")
    token = fencing_token
    for _ in range(max_steps):
        await db.refresh(run)
        if run.status not in {"running", "queued"}:
            break
        if run.cancel_requested:
            run = await step_once(db, run, fencing_token=token)
            break
        run = await step_once(db, run, fencing_token=token)
        if run.status != "running":
            break
        cp = loads(run.checkpoint_json, {})
        if cp.get("phase") == "done":
            break
    return run


async def start_and_run(
    db: AsyncSession,
    session: AgentSession,
    *,
    message: str,
    provider: str = "mock",
    max_rounds: int = 8,
    token_budget: int = 0,
) -> AgentRun:
    run = await create_run(
        db,
        session,
        message=message,
        provider=provider,
        max_rounds=max_rounds,
        token_budget=token_budget,
    )
    claimed, token = await claim_run(db, run.id)
    if not claimed:
        return run
    return await execute_until_idle(db, run.id, fencing_token=token)


async def resume_run(db: AsyncSession, run: AgentRun) -> AgentRun:
    if run.status in {"success", "cancelled"}:
        raise HTTPException(400, "run 已结束，无法恢复")
    if run.status == "paused_budget":
        raise HTTPException(400, "预算暂停，请提高预算后新建 run")
    session = await db.get(AgentSession, run.session_id)
    if session and session.active_run_id and session.active_run_id != run.id:
        other = await db.get(AgentRun, session.active_run_id)
        if other and other.status in {"queued", "running", "waiting"}:
            raise HTTPException(409, "会话另有活跃 run")
    run.cancel_requested = False
    run.error_code = ""
    run.error_message = ""
    run.status = "queued"
    run.finished_at = None
    if session:
        session.active_run_id = run.id
    await append_event(db, run, "run.resume", {"checkpoint_phase": loads(run.checkpoint_json, {}).get("phase")})
    await db.flush()
    claimed, token = await claim_run(db, run.id)
    if not claimed:
        return run
    return await execute_until_idle(db, run.id, fencing_token=token)


async def list_events(db: AsyncSession, run_id: int, after_seq: int = 0) -> list[AgentEvent]:
    q = (
        select(AgentEvent)
        .where(AgentEvent.run_id == run_id, AgentEvent.seq > after_seq)
        .order_by(AgentEvent.seq.asc())
    )
    return list((await db.execute(q)).scalars().all())
