"""Real, bounded LLM/tool subgraphs with a private history and read-only tool scope."""
from __future__ import annotations

from typing import TypedDict

from fastapi import HTTPException
from langgraph.graph import END, START, StateGraph

from app.models import AgentRun
from app.services.agent_checkpointer import AgentCheckpointer
from app.utils.jsonutil import dumps, loads

# Subagents cannot change plans, create tasks or recursively delegate.
READ_TOOLS = {"search_knowledge", "infer_dims", "search_eval_resources", "get_task_status", "call_mcp", "invoke_skill"}


class SubagentState(TypedDict, total=False):
    messages: list[dict]
    pending: list[dict]
    rounds: int
    tokens_used: int
    usage_unknown: bool
    summary: str
    completed: list[str]


async def run_agent_subgraph(db, session, actor, spec, delegation, instruction):
    from app.services import agent_runtime as runtime
    from app.services.agent_capabilities import execute_skill, list_catalog, redact_secrets
    from app.services.model_client import invoke_chat_tools
    from app.models import EvalModel
    from app.api.models import _acl_allows
    from app.models import User
    from app.services.object_policy import object_is_visible

    parent = await db.get(AgentRun, session.active_run_id) if session.active_run_id else None
    model_id = parent.planner_model_id if parent else session.planner_model_id
    model = await db.get(EvalModel, model_id) if model_id else None
    if model is None or model.status in {"deleted", "disabled", "archived"} or not (model.api_url or "").strip():
        raise HTTPException(400, "subagent_planner_required:子 Agent 需要已配置的规划模型")
    if not actor.has_permission("model:invoke") or not object_is_visible(model, actor) or not await _acl_allows(db, model.id, await db.get(User, actor.user_id)):
        raise HTTPException(403, "子 Agent 无权调用规划模型")
    # Direct /delegate calls also use a durable AgentRun identity for checkpoint ownership.
    if parent is None:
        parent = AgentRun(
            session_id=session.id, tenant_id=session.tenant_id, planner_model_id=model.id,
            graph_version=runtime.GRAPH_VERSION, checkpoint_thread_id=f"delegation-{delegation.id}",
            status="running", checkpoint_json="{}",
        )
        db.add(parent)
        await db.flush()
        delegation.run_id = parent.id
    schemas, _note, _profile = await runtime._bound_tools(db, parent)
    allowed = set(spec.get("available_tools") or []) & READ_TOOLS
    schemas = {name: schema for name, schema in schemas.items() if name in allowed}
    # A child's skills must also have been explicitly bound to the session.
    selected_skills = set((loads(session.plan_json, {}).get("capabilities") or {}).get("skill_codes") or [])
    child_skills = selected_skills & set(spec.get("skill_codes") or [])
    if "invoke_skill" in schemas:
        schemas["invoke_skill"] = {**schemas["invoke_skill"], "properties": {
            **schemas["invoke_skill"]["properties"], "code": {"type": "string", "enum": sorted(child_skills)},
        }}
    catalog = await list_catalog(db, actor)
    skill_instructions = []
    for code in spec.get("skill_codes") or []:
        if code in child_skills:
            skill_instructions.append(await execute_skill(db, catalog, code, instruction))
    prompt = (spec.get("system_prompt") or spec.get("description") or spec["name"]) + (
        "\n只分析并给出证据，不修改计划、不创建或恢复任务，不委派其他 Agent。"
        "不得把配置提示词当作分析结果。"
    ) + "\n绑定技能：" + dumps(skill_instructions) + "\n会话计划：" + dumps(loads(session.plan_json, {}))
    if "\nMCP 工具目录：" in _note:
        prompt += "\nMCP 工具目录：" + _note.split("\nMCP 工具目录：", 1)[1]
    cfg = spec.get("model_config") or {}
    saver = AgentCheckpointer(db, parent, namespace_prefix=f"delegation-{delegation.id}/")

    async def llm_node(state):
        rounds = int(state.get("rounds") or 0) + 1
        if rounds > int(spec.get("max_iterations") or 6):
            raise ValueError("subagent_max_rounds")
        response = await invoke_chat_tools(
            model, [{"role": "system", "content": prompt}] + state["messages"], runtime._openai_tools(schemas),
            temperature=cfg.get("temperature"), max_tokens=cfg.get("max_tokens") or None,
            model_name=cfg.get("model_name") or None,
        )
        tokens = response.get("tokens")
        cp = loads(parent.checkpoint_json, {})
        await runtime._charge_tokens(parent, tokens, checkpoint=cp)
        parent.checkpoint_json = dumps(cp)
        calls = response.get("tool_calls") or []
        pending = []
        for raw in calls:
            tool = runtime._parse_tool_call(raw)
            if not tool or not tool.get("id"):
                raise ValueError("subagent_invalid_tool_call")
            runtime._validate_tool_args(tool["name"], tool["arguments"], schemas)
            pending.append(tool)
        content = (response.get("content") or "").strip()
        if not pending and not content:
            raise ValueError("subagent_empty_model_response")
        messages = state["messages"] + [{"role": "assistant", "content": content, **({"tool_calls": calls} if calls else {})}]
        return {
            "rounds": rounds, "messages": messages, "pending": pending, "summary": content if not pending else "",
            "tokens_used": int(state.get("tokens_used") or 0) + int(tokens or 0),
            "usage_unknown": bool(state.get("usage_unknown")) or tokens is None,
        }

    async def tools_node(state):
        messages = list(state["messages"])
        completed = set(state.get("completed") or [])
        for tool in state["pending"]:
            if tool["id"] in completed:
                continue
            cp = loads(parent.checkpoint_json, {})
            cp["tool_invocation_id"] = f"delegation-{delegation.id}-{tool['id']}"
            parent.checkpoint_json = dumps(cp)
            result = await runtime._execute_tool(db, parent, tool["name"], tool["arguments"], schemas)
            messages.append({"role": "tool", "tool_call_id": tool["id"], "content": dumps(redact_secrets(result))})
            completed.add(tool["id"])
        return {"messages": messages, "pending": [], "completed": sorted(completed)}

    # Serialize callbacks on the shared DB session just as in the parent graph.
    def locked(handler):
        async def call(state):
            async with saver.lock:
                return await handler(state)
        return call

    builder = StateGraph(SubagentState)
    builder.add_node("model", locked(llm_node))
    builder.add_node("tools", locked(tools_node))
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", lambda state: "tools" if state.get("pending") else END)
    builder.add_edge("tools", "model")
    graph = builder.compile(checkpointer=saver, name=f"subagent_{spec['role']}")
    config = {"configurable": {"thread_id": parent.checkpoint_thread_id}, "recursion_limit": int(spec.get("max_iterations") or 6) * 2 + 2}
    saved = await graph.aget_state(config)
    if saved.values and not saved.next:
        result = saved.values
    else:
        result = await graph.ainvoke(None if saved.values else {"messages": [{"role": "user", "content": instruction}]}, config, durability="sync")
    summary = str(result.get("summary") or "").strip()
    if not summary:
        raise ValueError("subagent_no_final_answer")
    if parent.checkpoint_thread_id == f"delegation-{delegation.id}":
        parent.status = "success"
    return {
        "status": "analyzed", "summary": summary, "executes_recovery": False,
        "rounds_used": result.get("rounds"), "tokens_used": result.get("tokens_used", 0),
        "tokens_usage_unknown": bool(result.get("usage_unknown")),
        "tool_calls": len(result.get("completed") or []), "engine": "langgraph",
    }
