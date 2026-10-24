"""LangGraph Agent runtime, retaining platform approvals, events and task execution."""
from __future__ import annotations

import os
import asyncio
import socket
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentEvent, AgentRun, AgentSession, AgentMessage
from app.utils.jsonutil import dumps, loads

# A node may await a configured 600s subagent; reserve a small recovery margin.
LEASE_SECONDS = 660
GRAPH_VERSION = "langgraph-v1"

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


def _validate_tool_args(name: str, args: Any, schemas: dict | None = None) -> None:
    from jsonschema import Draft202012Validator

    table = TOOL_SCHEMAS if schemas is None else schemas
    if name not in table:
        raise ValueError(f"unknown_tool:{name}")
    schema = table[name]
    if not isinstance(args, dict):
        raise ValueError(f"invalid_tool_args:{name}")
    error = next(Draft202012Validator(schema).iter_errors(args), None)
    if error:
        # Never echo potentially sensitive argument values in error messages.
        raise ValueError(f"invalid_tool_schema:{name}:{error.validator}")


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
    cp = loads(run.checkpoint_json, {})
    return {
        "id": run.id,
        "session_id": run.session_id,
        "status": run.status,
        "provider": run.provider,
        "planner_model_id": run.planner_model_id,
        "graph_version": run.graph_version,
        "purpose": cp.get("purpose", "dialogue"),
        "input": cp.get("input") or "",
        "checkpoint": cp,
        "checkpoint_thread_id": run.checkpoint_thread_id,
        "lease_owner": run.lease_owner or "",
        "fencing_token": run.fencing_token or 0,
        "cancel_requested": bool(run.cancel_requested),
        "max_rounds": run.max_rounds,
        "rounds_used": run.rounds_used,
        "token_budget": run.token_budget,
        "tokens_used": run.tokens_used,
        "tokens_usage_unknown": bool(cp.get("tokens_usage_unknown")),
        "completion": cp.get("completion") or {"kind": "pending", "objective_verified": False},
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
    provider: str = "live",
    max_rounds: int = 8,
    token_budget: int = 0,
    client_message_id: str = "",
    planner_model_id: int | None = None,
    purpose: str = "dialogue",
    record_message: bool = True,
) -> AgentRun:
    """创建 run；若已有 active run 则 409。禁止 mock provider。"""
    message = message.strip()
    if session.active_run_id:
        active = await db.get(AgentRun, session.active_run_id)
        if active and active.status in {"queued", "running", "waiting"}:
            raise HTTPException(409, "会话已有活跃 run，禁止并发启动")

    if provider == "mock":
        raise HTTPException(400, "mock_provider_removed:禁止 Mock，请使用 live + 已配置规划模型")
    if provider != "live":
        raise HTTPException(400, "provider 仅支持 live")

    mid = planner_model_id or getattr(session, "planner_model_id", None)
    if purpose == "followup" and not session.task_id:
        raise HTTPException(400, "执行跟踪需要已关联的实际任务")
    if not mid:
        raise HTTPException(400, "planner_model_id_required:请指定已配置 api_url 的规划模型")
    from app.models import EvalModel

    model = await db.get(EvalModel, int(mid))
    if not model or model.status in {"deleted", "disabled", "archived"} or not (model.api_url or "").strip():
        raise HTTPException(400, "planner_model_misconfigured:规划模型不存在或未配置 api_url")

    prior_rows = list(
        (
            await db.execute(
                select(AgentMessage).where(AgentMessage.session_id == session.id).order_by(AgentMessage.id.desc()).limit(16)
            )
        ).scalars().all()
    )
    history = []
    for item in reversed(prior_rows):
        content = (item.content or "").strip()
        if not content:
            continue
        role = "assistant" if item.role in {"main", "monitor", "diagnose"} else "user"
        history.append({"role": role, "content": content if not record_message and role == "user" and content == message else content[:2000]})
    if record_message or not any(item["role"] == "user" and item["content"] == message for item in history):
        history.append({"role": "user", "content": message})
    checkpoint = _default_checkpoint(message)
    checkpoint["messages"] = history
    checkpoint["input"] = message
    checkpoint["purpose"] = purpose
    if purpose == "planning":
        checkpoint["phase"] = "prepare"
    elif purpose == "followup":
        checkpoint["phase"] = "verify"
    thread = f"sess-{session.id}-{uuid.uuid4().hex[:12]}"
    run = AgentRun(
        session_id=session.id,
        tenant_id=session.tenant_id,
        status="queued",
        graph_version=GRAPH_VERSION,
        provider="live",
        planner_model_id=int(mid),
        checkpoint_json=dumps(checkpoint),
        checkpoint_thread_id=thread,
        max_rounds=max(1, int(max_rounds or 8)),
        token_budget=max(0, int(token_budget or 0)),
    )
    db.add(run)
    await db.flush()
    session.active_run_id = run.id
    session.planner_model_id = int(mid)
    session.row_version = int(session.row_version or 0) + 1
    session.updated_at = datetime.utcnow()
    if record_message:
        db.add(AgentMessage(session_id=session.id, role="system" if purpose == "followup" else "user", content=message, tool_name="", payload_json=dumps({"client_message_id": client_message_id, "run_id": run.id, "purpose": purpose})))
    await append_event(db, run, "run.created", {"provider": "live", "planner_model_id": int(mid), "message": message[:200]})
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
    claimed = await db.execute(
        update(AgentRun).where(
            AgentRun.id == run_id,
            AgentRun.status.in_(["queued", "waiting"]),
            AgentRun.fencing_token == int(run.fencing_token or 0),
        ).values(
            fencing_token=token, lease_owner=owner,
            lease_until=datetime.utcnow() + timedelta(seconds=LEASE_SECONDS), status="running",
        ).execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        return None, 0
    await db.refresh(run)
    run.row_version = int(run.row_version or 0) + 1
    await append_event(db, run, "run.claimed", {"owner": owner, "fencing_token": token})
    await db.flush()
    return run, token


async def _clear_active(db: AsyncSession, run: AgentRun) -> None:
    session = await db.get(AgentSession, run.session_id)
    if session and run.status in {"failed", "paused_budget", "cancelled"}:
        plan = loads(session.plan_json, {})
        if plan.get("analysis_status") == "pending" and plan.get("planning_run_id") == run.id:
            plan["analysis_status"] = "failed"
            session.plan_json = dumps(plan)
    if session and session.active_run_id == run.id:
        session.active_run_id = None
        session.row_version = int(session.row_version or 0) + 1


async def request_cancel(db: AsyncSession, run: AgentRun) -> AgentRun:
    if run.status in {"success", "failed", "cancelled", "paused_budget"}:
        raise HTTPException(400, "run 已结束")
    # Wait for the current writer, then refresh its event cursor before appending.
    # A stale ORM instance must not overwrite events committed by an in-flight node.
    await db.execute(update(AgentRun).where(AgentRun.id == run.id, AgentRun.status.in_(["queued", "running", "waiting"]))
                     .values(cancel_requested=True).execution_options(synchronize_session=False))
    await db.refresh(run)
    if run.status in {"success", "failed", "cancelled", "paused_budget"}:
        return run
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


def _openai_tools(schemas: dict | None = None) -> list[dict]:
    table = TOOL_SCHEMAS if schemas is None else schemas
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": name,
                "parameters": schema,
            },
        }
        for name, schema in table.items()
    ]


async def _bound_tools(db: AsyncSession, run: AgentRun) -> tuple[dict, str, dict]:
    session = await db.get(AgentSession, run.session_id)
    plan = loads(session.plan_json, {}) if session else {}
    bound = plan.get("capabilities") or {}
    roles = list(bound.get("subagent_roles") or ["monitor", "diagnose"])
    skills = list(bound.get("skill_codes") or [])
    mcps = list(bound.get("mcp_resource_ids") or [])
    schemas = dict(TOOL_SCHEMAS)
    schemas["delegate_agent"] = {
        "type": "object",
        "properties": {"role": {"type": "string", "enum": roles}, "input": {"type": "string"}},
        "required": ["role"],
        "additionalProperties": False,
    }
    if skills:
        schemas["invoke_skill"] = {
            "type": "object",
            "properties": {"code": {"type": "string"}, "input": {"type": "string"}},
            "required": ["code"],
            "additionalProperties": False,
        }
    if mcps:
        schemas["call_mcp"] = {
            "type": "object",
            "properties": {
                "resource_id": {"type": "string"},
                "tool_name": {"type": "string"},
                "arguments": {"type": "object"},
            },
            "required": ["resource_id", "tool_name"],
            "additionalProperties": False,
        }
    schemas["search_eval_resources"] = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "kind": {"type": "string"},
        },
        "required": ["query"],
        "additionalProperties": False,
    }
    schemas["get_task_status"] = {"type": "object", "properties": {}, "additionalProperties": False}
    schemas["get_resource_inventory"] = {"type": "object", "properties": {}, "additionalProperties": False}
    schemas["get_task_evidence"] = {"type": "object", "properties": {"max_samples": {"type": "integer", "minimum": 1, "maximum": 50}}, "additionalProperties": False}
    schemas["request_task_execution"] = {"type": "object", "properties": {}, "additionalProperties": False}
    schemas["propose_resources"] = {
        "type": "object",
        "properties": {
            "dataset_id": {"type": "integer"},
            "model_id": {"type": "integer"},
            "judge_resource_id": {"type": "string"},
            "trial_run": {"type": "boolean"},
            "token_budget": {"type": "integer", "minimum": 0},
            "scene": {"type": "string"},
        },
        "additionalProperties": False,
    }
    from app.services.agent_capabilities import filter_tool_schemas, get_main_profile

    profile = await get_main_profile(db, getattr(session, "tenant_id", None) if session else None)
    schemas = filter_tool_schemas(schemas, profile.get("available_tools"))
    planner_id = getattr(session, "planner_model_id", None) if session else None
    binding = (
        f"已启用子 Agent：{', '.join(roles)}。"
        f"已启用编排 Skill：{', '.join(skills) or '无'}。"
        f"已启用 MCP：{', '.join(mcps) or '无'}。"
        f"当前计划：场景 {plan.get('scene') or '未定'}，数据集 id={plan.get('dataset_id') or '未选'}，"
        f"被测模型 id={plan.get('model_id') or '未选'}，打分工具 {plan.get('judge_resource_id') or '未选'}。"
        + (f"规划模型 id={planner_id} 只能用来编排，不能写入被测模型。" if planner_id else "")
        + "用户补充评测对象、数据集、被测模型或打分工具时，先调用 search_eval_resources 找到真实 ID，再调用 propose_resources 写进计划。"
        "用户补充试跑/正式模式或Token预算时，也通过propose_resources的trial_run、token_budget写入；不要只口头确认。未调用 propose_resources 时，不要声称计划已经改好。"
        "专项分析调用 delegate_agent。异常诊断只返回建议，不能执行恢复或补测。"
        "技能调用 invoke_skill。MCP 只能调用已启用连接上的工具。"
        "MCP 工具参数见下方目录，调用时必须填写 arguments。"
        "需要执行评测时调用 request_task_execution 等待用户审批；不得声称任务已执行。"
        "通过 get_task_status 查询实际状态，只有任务真实完成才可声称完成评测。"
        "也可以调用 search_knowledge 或 infer_dims。信息足够时直接回复。"
        "不得读取系统凭证；外部调用只走已授权工具。"
    )
    note = f"{profile.get('system_prompt') or ''}\n\n{binding}".strip()
    from app.services.agent_context import resource_inventory
    from app.services.agent_capabilities import list_catalog

    actor = await runtime_actor(db, run)
    inventory = loads(run.checkpoint_json, {}).get("resource_inventory") or await resource_inventory(db, actor, limit=24)
    note += "\n平台授权资源（真实ID、名称、状态与版本）：" + dumps(inventory)
    catalog = await list_catalog(db, actor)
    note += "\n已启用角色用途与阶段：" + dumps([{k: spec.get(k) for k in ("role", "name", "description", "evaluation_spec")} for spec in catalog["subagents"] if spec["role"] in roles])
    note += "\n监控、诊断、报告审校和报告优化在任务开始后由平台跟进触发；规划阶段不要对无任务角色空调用。首次计划请核对授权资源并按需用propose_resources选择真实ID，汇总已有子Agent分析后再给计划摘要。"
    if mcps:
        from app.models import BaseResource, ResourceEvent
        from app.services.object_policy import object_is_visible

        actor = await runtime_actor(db, run)
        catalog = []
        for resource_id in mcps:
            resource = await db.scalar(select(BaseResource).where(BaseResource.resource_id == resource_id))
            if not object_is_visible(resource, actor):
                continue
            event = await db.scalar(select(ResourceEvent).where(
                ResourceEvent.resource_id == resource_id, ResourceEvent.event_type == "mcp.catalog",
            ).order_by(ResourceEvent.id.desc()).limit(1))
            payload = loads(event.payload_json, {}) if event else {}
            catalog.append({"resource_id": resource_id, "tools": payload.get("tools") or []})
        note += "\nMCP 工具目录：" + dumps(catalog)
    return schemas, note, profile


async def runtime_actor(db: AsyncSession, run: AgentRun):
    """Re-evaluate the creator's current identity; a runtime never becomes an admin."""
    from app.models import User
    from app.services.actor_context import build_actor
    from app.services.object_policy import object_is_visible

    session = await db.get(AgentSession, run.session_id)
    user = await db.get(User, session.creator_id) if session and session.creator_id else None
    if user is None or user.status != "active":
        raise ValueError("agent_actor_unavailable")
    actor = await build_actor(db, user)
    if not object_is_visible(session, actor) or not actor.has_permission("agent:invoke"):
        raise ValueError("agent_actor_forbidden")
    return actor


def _parse_tool_call(raw: dict) -> dict | None:
    if not raw:
        return None
    fn = raw.get("function") or {}
    name = fn.get("name") or raw.get("name")
    if not name:
        return None
    args_raw = fn.get("arguments") if "function" in raw else raw.get("arguments")
    if isinstance(args_raw, str):
        args = loads(args_raw, {})
    elif isinstance(args_raw, dict):
        args = args_raw
    else:
        args = {}
    return {"name": name, "arguments": args, "id": raw.get("id") or ""}


async def _live_select_tool(db: AsyncSession, run: AgentRun, checkpoint: dict, schemas: dict, capability_note: str, model_config: dict | None = None) -> tuple[dict | None, dict]:
    """调用真实规划模型选工具；返回 (tool|None, llm_meta)。禁止降级 mock。"""
    from app.models import EvalModel
    from app.services.model_client import invoke_chat_tools

    if not run.planner_model_id:
        raise RuntimeError("planner_model_id_required")
    model = await db.get(EvalModel, int(run.planner_model_id))
    if not model or model.status in {"deleted", "disabled", "archived"} or not (model.api_url or "").strip():
        raise RuntimeError("planner_model_misconfigured")
    from app.api.models import _acl_allows
    from app.models import User
    from app.services.object_policy import object_is_visible

    actor = await runtime_actor(db, run)
    if not actor.has_permission("model:invoke") or not object_is_visible(model, actor) or not await _acl_allows(db, model.id, await db.get(User, actor.user_id)):
        raise ValueError("planner_model_forbidden")

    messages: list[dict] = [
        {
            "role": "system",
            "content": capability_note,
        }
    ]
    seen_tool_ids = set()
    for m in checkpoint.get("messages") or []:
        role = m.get("role") or "user"
        item = {"role": role, "content": m.get("content") or ""}
        if role == "assistant" and m.get("tool_calls"):
            item["tool_calls"] = m["tool_calls"]
        if role == "tool":
            item["tool_call_id"] = m.get("tool_call_id") or ""
            seen_tool_ids.add(item["tool_call_id"])
        messages.append(item)
    for obs in checkpoint.get("observations") or []:
        tid = obs.get("tool_call_id") or ""
        if tid in seen_tool_ids:
            continue
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tid or "obs",
                "content": dumps(obs.get("result") or {}),
            }
        )
    cfg = model_config or {}
    from app.services.agent_capabilities import redact_secrets
    await append_event(db, run, "llm.request", {"messages": redact_secrets(messages), "tools": list(schemas), "round": run.rounds_used})
    llm = await invoke_chat_tools(
        model,
        messages,
        _openai_tools(schemas),
        temperature=cfg.get("temperature"),
        max_tokens=cfg.get("max_tokens") or None,
        model_name=cfg.get("model_name") or None,
    )
    tool_calls = llm.get("tool_calls") or []
    parsed = []
    for raw in tool_calls:
        tool = _parse_tool_call(raw)
        if tool:
            parsed.append(tool)
    if parsed:
        return parsed, llm
    if llm.get("content"):
        checkpoint["pending_reply"] = llm["content"]
    return [], llm


async def _execute_tool(db: AsyncSession, run: AgentRun, name: str, args: dict, schemas: dict) -> dict:
    _validate_tool_args(name, args, schemas)
    actor = await runtime_actor(db, run)
    if name == "get_resource_inventory":
        from app.services.agent_context import resource_inventory
        return await resource_inventory(db, actor)
    if name == "get_task_evidence":
        from app.services.agent_context import task_evidence
        session = await db.get(AgentSession, run.session_id)
        return await task_evidence(db, session, actor, max_samples=int(args.get("max_samples") or 20))
    if name == "search_knowledge":
        from app.services.agent_tools import search_knowledge

        items = await search_knowledge(db, args.get("query") or "", tenant_id=actor.tenant_id)
        return {"items": items[:5], "count": len(items)}
    if name == "infer_dims":
        from app.services.agent_orchestrator import infer_dims

        scene, industry = infer_dims(args.get("text") or "")
        return {"scene": scene, "industry": industry}
    if name == "search_eval_resources":
        from app.services.agent_orchestrator import search_eval_resources

        return await search_eval_resources(db, args.get("query") or "", str(args.get("kind") or ""), actor=actor)
    if name == "propose_resources":
        from app.services.agent_orchestrator import apply_resource_proposal

        session = await db.get(AgentSession, run.session_id)
        if session is None:
            raise ValueError("session_missing")
        try:
            return await apply_resource_proposal(db, session, args, actor=actor)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
    if name == "delegate_agent":
        from app.services.agent_capabilities import run_subagent

        session = await db.get(AgentSession, run.session_id)
        if session is None:
            raise ValueError("session_missing")
        try:
            out = await run_subagent(db, session, actor, str(args.get("role") or ""), instruction=str(args.get("input") or ""))
        except HTTPException as exc:
            raise ValueError(str(exc.detail)) from exc
        return {"delegation_id": out.get("delegation_id"), "role": out.get("role"), "result": out.get("result")}
    if name == "invoke_skill":
        from app.services.agent_capabilities import execute_skill, list_catalog

        session = await db.get(AgentSession, run.session_id)
        plan = loads(session.plan_json, {}) if session else {}
        selected = (plan.get("capabilities") or {}).get("skill_codes") or []
        code = str(args.get("code") or "")
        if code not in selected:
            raise ValueError(f"skill_not_enabled:{code}")
        catalog = await list_catalog(db, actor)
        try:
            return await execute_skill(db, catalog, code, str(args.get("input") or ""))
        except HTTPException as exc:
            raise ValueError(str(exc.detail)) from exc
    if name == "call_mcp":
        from app.services.tool_gateway import invoke_tool, response_result

        session = await db.get(AgentSession, run.session_id)
        plan = loads(session.plan_json, {}) if session else {}
        selected = (plan.get("capabilities") or {}).get("mcp_resource_ids") or []
        resource_id = str(args.get("resource_id") or "")
        tool_name = str(args.get("tool_name") or "")
        if resource_id not in selected:
            raise ValueError(f"mcp_not_enabled:{resource_id}")
        if not actor.has_permission("resource:invoke"):
            raise ValueError("resource_invoke_forbidden")
        from app.models import ResourceEvent
        from jsonschema import Draft202012Validator
        from referencing import Registry

        catalog_event = await db.scalar(select(ResourceEvent).where(
            ResourceEvent.resource_id == resource_id, ResourceEvent.event_type == "mcp.catalog",
        ).order_by(ResourceEvent.id.desc()).limit(1))
        catalog = loads(catalog_event.payload_json, {}) if catalog_event else {}
        tool = next((item for item in catalog.get("tools", []) if item.get("name") == tool_name), None)
        if tool is None:
            raise ValueError("mcp_tool_catalog_required:请先探测连接以获取工具参数")
        arguments = args.get("arguments", {})
        schema = tool.get("inputSchema") or {"type": "object"}
        if next(Draft202012Validator(schema, registry=Registry()).iter_errors(arguments), None):
            raise ValueError("invalid_mcp_arguments")
        cp = loads(run.checkpoint_json, {})
        envelope = await invoke_tool(
            db,
            actor=actor,
            resource_id=resource_id,
            body={"method": "tools/call", "params": {"name": tool_name, "arguments": arguments}},
            correlation_id=cp.get("tool_invocation_id") or f"agent-{run.id}-{uuid.uuid4().hex}",
            caller_id="agent_runtime",
        )
        if (envelope.get("body") or {}).get("status") == "error":
            from app.services.redaction import safe_error_message

            error = (envelope.get("body") or {}).get("error") or {}
            # Business errors are observations the model can correct, never a successful tool result.
            return {"resource_id": resource_id, "tool_name": tool_name, "error": {
                "code": error.get("code") or "mcp_failed",
                "message": safe_error_message(error.get("message") or "mcp failed"),
            }}
        return {"resource_id": resource_id, "tool_name": tool_name, "result": response_result(envelope)}
    if name == "get_task_status":
        from app.services.agent_graph import task_completion

        return await task_completion(db, run)
    if name == "request_task_execution":
        from app.services.goal_spec import canonical_plan_hash

        session = await db.get(AgentSession, run.session_id)
        plan = loads(session.plan_json, {})
        if not plan.get("ready"):
            raise ValueError("plan_not_ready")
        if not actor.has_permission("agent:confirm"):
            raise ValueError("agent_confirm_forbidden")
        if loads(run.checkpoint_json, {}).get("purpose") == "planning":
            plan["analysis_status"] = "complete"
            plan["planning_run_id"] = run.id
            session.plan_json = dumps(plan)
        return {"approval_required": True, "plan_hash": canonical_plan_hash(plan)}
    raise ValueError(f"unknown_tool:{name}")


async def _charge_tokens(
    run: AgentRun,
    n: int | None,
    *,
    unknown: bool = False,
    checkpoint: dict | None = None,
) -> None:
    if unknown or n is None:
        if checkpoint is not None:
            checkpoint["tokens_usage_unknown"] = True
        else:
            cp = loads(run.checkpoint_json, {})
            cp["tokens_usage_unknown"] = True
            run.checkpoint_json = dumps(cp)
        return
    run.tokens_used = int(run.tokens_used or 0) + max(0, int(n))
    if run.token_budget and run.tokens_used > run.token_budget:
        raise PermissionError("budget_exceeded")


async def _select_tool_node(db: AsyncSession, run: AgentRun, cp: dict) -> AgentRun:
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

    schemas, capability_note, profile = await _bound_tools(db, run)
    try:
        tools, llm_meta = await asyncio.wait_for(_live_select_tool(
            db, run, cp, schemas, capability_note, profile.get("model_config")
        ), timeout=int(profile.get("timeout_seconds") or 120))
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error_code = "planner_unavailable"
        from app.services.redaction import safe_error_message
        run.error_message = safe_error_message(exc)[:300]
        run.finished_at = datetime.utcnow()
        await append_event(db, run, "run.failed", {"error_code": "planner_unavailable"})
        await _clear_active(db, run)
        await db.flush()
        return run

    tokens = llm_meta.get("tokens")
    try:
        await _charge_tokens(run, tokens, unknown=tokens is None, checkpoint=cp)
    except PermissionError:
        run.status = "paused_budget"
        run.error_code = "budget_exceeded"
        run.error_message = "超过 token 预算"
        run.finished_at = datetime.utcnow()
        await append_event(db, run, "run.paused_budget", {"tokens_used": run.tokens_used,
                           "response_text": llm_meta.get("content") or "", "tool_calls": llm_meta.get("tool_calls") or []})
        await _clear_active(db, run)
        await db.flush()
        return run

    await append_event(
        db,
        run,
        "llm.select",
        {
            "finish_reason": llm_meta.get("finish_reason"),
            "tokens": tokens,
            "latency_ms": llm_meta.get("latency_ms"),
            "has_tool": bool(tools),
            "tools": [item.get("name") for item in tools],
            "preview": (llm_meta.get("content") or "")[:240],
            "response_text": llm_meta.get("content") or "",
            "tool_calls": llm_meta.get("tool_calls") or [],
        },
        step_id=f"r{run.rounds_used}",
    )

    if not tools:
        if not (llm_meta.get("content") or "").strip():
            run.status = "failed"
            run.error_code = "empty_model_response"
            run.error_message = "模型未返回工具调用或最终回答"
            run.finished_at = datetime.utcnow()
            await append_event(db, run, "run.failed", {"error_code": "empty_model_response"})
            await _clear_active(db, run)
            await db.flush()
            return run
        cp["phase"] = "reply"
        run.checkpoint_json = dumps(cp)
        await append_event(db, run, "llm.select_none", {})
    else:
        signature = dumps(
            [{"name": item.get("name"), "arguments": item.get("arguments") or {}} for item in tools]
        )
        seen = list(cp.get("call_signatures") or [])
        seen.append(signature)
        cp["call_signatures"] = seen[-12:]
        if seen.count(signature) >= 3:
            run.status = "failed"
            run.error_code = "loop_detected"
            run.error_message = "同一工具调用重复出现，已强制终止"
            run.finished_at = datetime.utcnow()
            await append_event(db, run, "run.failed", {"error_code": "loop_detected"})
            await _clear_active(db, run)
            await db.flush()
            return run
        for tool in tools:
            try:
                _validate_tool_args(tool["name"], tool.get("arguments") or {}, schemas)
            except ValueError as exc:
                run.status = "failed"
                run.error_code = "invalid_tool_schema"
                run.error_message = str(exc)
                run.finished_at = datetime.utcnow()
                await append_event(db, run, "tool.rejected", {"error": str(exc), "tool": tool})
                await _clear_active(db, run)
                await db.flush()
                return run
        msgs = list(cp.get("messages") or [])
        msgs.append({
            "role": "assistant",
            "content": llm_meta.get("content") or "",
            "tool_calls": llm_meta.get("tool_calls") or [],
        })
        cp["messages"] = msgs
        cp["pending_tools"] = tools
        cp["pending_tool"] = tools[0]
        cp["phase"] = "observe"
        run.checkpoint_json = dumps(cp)
        await append_event(db, run, "tool.selected", {"tools": tools}, step_id=f"r{run.rounds_used}")
    await db.flush()
    return run


async def _observe_node(db: AsyncSession, run: AgentRun, cp: dict) -> AgentRun:
    pending = list(cp.get("pending_tools") or [])
    if not pending and cp.get("pending_tool"):
        pending = [cp.get("pending_tool")]
    obs = list(cp.get("observations") or [])
    msgs = list(cp.get("messages") or [])
    completed = set(cp.get("completed_tool_ids") or [])
    try:
        for index, tool in enumerate(pending):
            tid = tool.get("id") or f"r{run.rounds_used}-{index}"
            if tid in completed:
                continue
            cp["tool_invocation_id"] = f"agent-{run.id}-{tid}"
            run.checkpoint_json = dumps(cp)
            name = tool.get("name") or ""
            args = tool.get("arguments") or {}
            schemas, _note, _profile = await _bound_tools(db, run)
            result = await _execute_tool(db, run, name, args, schemas)
            from app.services.agent_capabilities import redact_secrets

            result = redact_secrets(result)
            if loads(run.checkpoint_json, {}).get("tokens_usage_unknown"):
                cp["tokens_usage_unknown"] = True
            obs.append({"tool": name, "result": result, "tool_call_id": tid})
            msgs.append({"role": "tool", "tool_call_id": tid, "content": dumps(result)})
            completed.add(tid)
            cp.update(observations=obs, messages=msgs, completed_tool_ids=sorted(completed))
            if result.get("approval_required"):
                cp["approval_plan_hash"] = result["plan_hash"]
            run.checkpoint_json = dumps(cp)
            await append_event(db, run, "tool.failed" if result.get("error") else "tool.observed", {"tool": name, "result": result}, step_id=f"r{run.rounds_used}")
    except ValueError as exc:
        run.status = "failed"
        run.error_code = "tool_failed"
        run.error_message = str(exc)
        run.finished_at = datetime.utcnow()
        await append_event(db, run, "tool.failed", {"error": str(exc)})
        await _clear_active(db, run)
        await db.flush()
        return run
    cp["observations"] = obs
    cp["messages"] = msgs
    cp["pending_tool"] = None
    cp["pending_tools"] = []
    cp["phase"] = "await_approval" if cp.get("approval_plan_hash") else "select_tool"
    run.checkpoint_json = dumps(cp)
    await db.flush()
    return run


async def _reply_node(db: AsyncSession, run: AgentRun, cp: dict) -> AgentRun:
    reply = (cp.get("pending_reply") or "").strip()
    _schemas, _note, profile = await _bound_tools(db, run)
    from app.services.agent_capabilities import clip_to_token_budget

    reply, clipped = clip_to_token_budget(reply, int((profile.get("model_config") or {}).get("max_tokens") or 0))
    if not reply:
        run.status = "failed"
        run.error_code = "empty_model_response"
        run.error_message = "模型未返回最终回答"
        run.finished_at = datetime.utcnow()
        await append_event(db, run, "run.failed", {"error_code": "empty_model_response"})
        await _clear_active(db, run)
        await db.flush()
        return run
    cp["final_reply"] = reply
    if cp.get("purpose") == "planning":
        session = await db.get(AgentSession, run.session_id)
        plan = loads(session.plan_json, {})
        plan["analysis_status"] = "complete"
        plan["planning_run_id"] = run.id
        plan["analysis_summary"] = reply
        session.plan_json = dumps(plan)
    cp["phase"] = "verify"
    run.checkpoint_json = dumps(cp)
    await append_event(db, run, "llm.reply", {"reply": reply[:500], "clipped": clipped})
    await db.flush()
    return run


async def step_once(db: AsyncSession, run: AgentRun, *, fencing_token: int | None = None) -> AgentRun:
    from app.services.agent_graph import advance_graph

    return await advance_graph(db, run, fencing_token=fencing_token)


async def execute_until_idle(
    db: AsyncSession,
    run_id: int,
    *,
    fencing_token: int | None = None,
    max_steps: int = 128,
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
    if run.status == "running":
        run.status = "waiting"
        run.lease_owner = ""
        run.lease_until = None
        await append_event(db, run, "run.yielded", {"reason": "step_limit"})
    return run


async def start_and_run(
    db: AsyncSession,
    session: AgentSession,
    *,
    message: str,
    provider: str = "live",
    max_rounds: int = 8,
    token_budget: int = 0,
    planner_model_id: int | None = None,
    purpose: str = "dialogue",
) -> AgentRun:
    run = await create_run(
        db,
        session,
        message=message,
        provider=provider,
        max_rounds=max_rounds,
        token_budget=token_budget,
        planner_model_id=planner_model_id,
        purpose=purpose,
    )
    claimed, token = await claim_run(db, run.id)
    if not claimed:
        return run
    return await execute_until_idle(db, run.id, fencing_token=token)


async def resume_run(db: AsyncSession, run: AgentRun, *, execute: bool = True) -> AgentRun:
    if run.status in {"success", "cancelled"}:
        raise HTTPException(400, "run 已结束，无法恢复")
    if run.status == "paused_budget":
        raise HTTPException(400, "预算暂停，请提高预算后新建 run")
    if run.status == "running" and run.lease_until and run.lease_until > datetime.utcnow():
        raise HTTPException(409, "run 正在执行")
    from app.services.agent_graph import can_resume

    if not await can_resume(db, run):
        return run
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
    if not execute:
        return run
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
