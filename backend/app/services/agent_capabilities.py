"""编排能力：主 Agent 绑定的子 Agent、编排 Skill、MCP 与可复用经验。"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AgentDefinition,
    AgentDelegation,
    AgentMessage,
    AgentSession,
    BaseResource,
    EvalTask,
    OrchestrationProfile,
    OrchestrationRecipe,
    OrchestrationSkill,
)
from app.services.object_policy import apply_object_scope, object_is_visible
from app.utils.jsonutil import dumps, iso, loads

REQUIRED_ROLES = ("monitor", "diagnose")
ROLE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
MAIN_ROLE = "coordinator"
MAIN_TOOLS = (
    "search_knowledge",
    "infer_dims",
    "search_eval_resources",
    "propose_resources",
    "delegate_agent",
    "invoke_skill",
    "call_mcp",
)
_SECRET_KEYS = {"api_key", "secret", "password", "token", "authorization", "api-key"}
DEFAULT_MAIN_PROMPT = (
    "你是评测编排主 Agent，是用户唯一入口。"
    "你理解评测目标，选择数据集、被测模型和打分工具，并按需调用子 Agent、编排 Skill 和 MCP。"
    "异常诊断只返回建议，不能执行恢复或补测。信息足够时直接回复。"
)


def default_model_config() -> dict:
    return {"model_name": "", "temperature": 0, "max_tokens": 0}


def normalize_model_config(raw) -> dict:
    src = raw if isinstance(raw, dict) else {}
    name = str(src.get("model_name") or "")[:80]
    try:
        temperature = float(src.get("temperature") if src.get("temperature") is not None else 0)
    except (TypeError, ValueError):
        temperature = 0
    try:
        max_tokens = int(src.get("max_tokens") or 0)
    except (TypeError, ValueError):
        max_tokens = 0
    return {
        "model_name": name,
        "temperature": max(0.0, min(temperature, 2.0)),
        "max_tokens": max(0, min(max_tokens, 8192)),
    }


def clean_tool_names(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    names = []
    for item in raw:
        name = str(item or "").strip()
        if name in MAIN_TOOLS and name not in names:
            names.append(name)
    return names


def normalize_tool_names(raw) -> list[str]:
    names = clean_tool_names(raw)
    return names or list(MAIN_TOOLS)


def clean_skill_codes(raw, known: set[str]) -> list[str]:
    if not isinstance(raw, list):
        return []
    codes = []
    for item in raw:
        code = str(item or "").strip()
        if not code:
            continue
        if code not in known:
            raise HTTPException(400, f"未知编排 Skill：{code}")
        if code not in codes:
            codes.append(code)
    return codes


def filter_tool_schemas(schemas: dict, allowed: list[str] | None) -> dict:
    names = set(allowed or [])
    if not names:
        return dict(schemas)
    return {key: value for key, value in schemas.items() if key in names}


def redact_secrets(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if str(key).lower() in _SECRET_KEYS:
                out[key] = "[redacted]"
            else:
                out[key] = redact_secrets(item)
        return out
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def clip_to_token_budget(text: str, max_tokens: int) -> tuple[str, bool]:
    if int(max_tokens or 0) <= 0:
        return text, False
    limit = int(max_tokens) * 4
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _profile_out(row: OrchestrationProfile) -> dict:
    spec = loads(row.evaluation_spec_json, None) if (row.evaluation_spec_json or "").strip() else None
    return {
        "role": row.role or MAIN_ROLE,
        "system_prompt": row.system_prompt or DEFAULT_MAIN_PROMPT,
        "model_config": normalize_model_config(loads(row.model_config_json, {})),
        "available_tools": normalize_tool_names(loads(row.available_tools_json, [])),
        "max_iterations": int(row.max_iterations or 10),
        "supports_stream": bool(row.supports_stream),
        "human_in_the_loop": bool(row.human_in_the_loop),
        "evaluation_spec": spec if isinstance(spec, dict) else None,
        "timeout_seconds": int(row.timeout_seconds or 120),
    }


async def get_main_profile(db: AsyncSession, tenant_id: int | None) -> dict:
    row = await db.scalar(
        select(OrchestrationProfile).where(OrchestrationProfile.tenant_id == tenant_id)
        if tenant_id is not None
        else select(OrchestrationProfile).where(OrchestrationProfile.tenant_id.is_(None))
    )
    if row is None:
        row = OrchestrationProfile(
            role=MAIN_ROLE,
            system_prompt=DEFAULT_MAIN_PROMPT,
            model_config_json=dumps(default_model_config()),
            available_tools_json=dumps(list(MAIN_TOOLS)),
            max_iterations=10,
            supports_stream=False,
            human_in_the_loop=True,
            evaluation_spec_json="",
            timeout_seconds=120,
            tenant_id=tenant_id,
        )
        db.add(row)
        await db.flush()
    return _profile_out(row)


async def update_main_profile(db: AsyncSession, tenant_id: int | None, body: dict) -> dict:
    await get_main_profile(db, tenant_id)
    row = await db.scalar(
        select(OrchestrationProfile).where(OrchestrationProfile.tenant_id == tenant_id)
        if tenant_id is not None
        else select(OrchestrationProfile).where(OrchestrationProfile.tenant_id.is_(None))
    )
    prompt = (body.get("system_prompt") or "").strip()
    row.system_prompt = (prompt or DEFAULT_MAIN_PROMPT)[:4000]
    row.model_config_json = dumps(normalize_model_config(body.get("model_config")))
    row.available_tools_json = dumps(normalize_tool_names(body.get("available_tools")))
    try:
        iterations = int(body.get("max_iterations") or 10)
    except (TypeError, ValueError):
        iterations = 10
    row.max_iterations = max(1, min(iterations, 20))
    row.supports_stream = bool(body.get("supports_stream"))
    row.human_in_the_loop = bool(body.get("human_in_the_loop"))
    spec = body.get("evaluation_spec")
    if spec in (None, "", {}):
        row.evaluation_spec_json = ""
    elif not isinstance(spec, dict):
        raise HTTPException(400, "evaluation_spec 须为对象")
    else:
        row.evaluation_spec_json = dumps(spec)[:4000]
    try:
        timeout = int(body.get("timeout_seconds") or 120)
    except (TypeError, ValueError):
        timeout = 120
    row.timeout_seconds = max(5, min(timeout, 600))
    row.updated_at = datetime.utcnow()
    await db.flush()
    return _profile_out(row)
SKILL_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
TRIGGER_TYPES = {"keyword", "intent", "entity", "context", "manual"}
EXECUTION_TYPES = {"prompt_template", "workflow", "code", "agent"}

BUILTIN_SUBAGENTS = [
    {
        "role": "monitor",
        "name": "监控分析 Agent",
        "required": True,
        "background": True,
        "human_in_the_loop": False,
        "max_iterations": 6,
        "description": "按任务跟踪状态、进度、风险趋势，并把异常状态交回主 Agent。不改优先级、不取消任务。",
        "duties": ["任务状态订阅或查询", "进度摘要", "风险趋势", "异常状态上报"],
    },
    {
        "role": "diagnose",
        "name": "异常诊断 Agent",
        "required": True,
        "background": False,
        "human_in_the_loop": True,
        "max_iterations": 6,
        "description": "分析失败、中断和日志。只给出原因、影响和恢复建议，不直接执行恢复或补测。",
        "duties": ["错误日志分析", "失败原因定位", "影响范围", "恢复建议", "补测建议"],
    },
    {
        "role": "plan_analyst",
        "name": "评测方案分析 Agent",
        "required": False,
        "background": False,
        "human_in_the_loop": False,
        "max_iterations": 6,
        "description": "核对目标、数据集、模型和资源缺口，给出可执行的方案差异。不创建任务。",
        "duties": ["覆盖缺口", "资源适配", "试跑或正式建议"],
    },
    {
        "role": "report_reviewer",
        "name": "报告审校 Agent",
        "required": False,
        "background": False,
        "human_in_the_loop": False,
        "max_iterations": 6,
        "description": "对照任务统计核对报告口径。不改分数，也不对外发布。",
        "duties": ["统计核对", "遗漏检查", "引用是否指向本任务"],
    },
    {
        "role": "param_advisor",
        "name": "参数推荐 Agent",
        "required": False,
        "background": False,
        "human_in_the_loop": False,
        "max_iterations": 6,
        "description": "根据目标、资源缺口和历史经验推荐预算、试跑开关和裁判，供主 Agent 写入计划。",
        "duties": ["预算建议", "试跑建议", "裁判建议"],
    },
]

BUILTIN_SKILLS = [
    {
        "code": "clarify_goal",
        "name": "目标澄清",
        "description": "把自然语言目标整理成场景、对象和成功标准。",
        "trigger_type": "context",
        "trigger_value": "",
        "execution_type": "prompt_template",
        "entry_point": "请只根据用户目标列出：评测对象、场景、成功标准、仍缺的参数。不要编造资源 ID。",
        "chainable": True,
    },
    {
        "code": "recommend_params",
        "name": "参数推荐",
        "description": "结合知识库与当前计划缺口，推荐预算和试跑策略。",
        "trigger_type": "context",
        "trigger_value": "",
        "execution_type": "workflow",
        "entry_point": "knowledge.search",
        "chainable": True,
    },
    {
        "code": "similar_case",
        "name": "相似案例",
        "description": "检索经验知识库中的历史任务与异常策略。",
        "trigger_type": "context",
        "trigger_value": "",
        "execution_type": "workflow",
        "entry_point": "knowledge.search",
        "chainable": True,
    },
    {
        "code": "draft_report",
        "name": "报告草稿",
        "description": "根据已有任务统计起草解释文字。数字以任务结果为准。",
        "trigger_type": "context",
        "trigger_value": "",
        "execution_type": "prompt_template",
        "entry_point": "用任务统计解释结果。没有证据的数字写成不可判定。不要改写分数。",
        "chainable": False,
    },
]


def _builtin_agent_out(item: dict) -> dict:
    return {
        **item,
        "builtin": True,
        "system_prompt": item["description"],
        "model_config": default_model_config(),
        "available_tools": ["search_knowledge"],
        "skill_codes": [],
        "supports_stream": False,
        "evaluation_spec": None,
        "enabled": True,
        "persisted": False,
    }


def _builtin_skill_out(item: dict) -> dict:
    return {**item, "builtin": True, "id": None, "enabled": True, "persisted": False}


def _builtin_agent_item(role: str) -> dict | None:
    for item in BUILTIN_SUBAGENTS:
        if item["role"] == role:
            return item
    return None


def _builtin_skill_item(code: str) -> dict | None:
    for item in BUILTIN_SKILLS:
        if item["code"] == code:
            return item
    return None


def _agent_out(row: AgentDefinition) -> dict:
    origin = _builtin_agent_item(row.role)
    return {
        "id": row.id,
        "role": row.role,
        "name": row.name,
        "required": bool(origin and origin["required"]),
        "background": bool(origin and origin["background"]),
        "builtin": origin is not None,
        "persisted": True,
        "enabled": bool(getattr(row, "enabled", True)),
        "human_in_the_loop": bool(row.human_in_the_loop),
        "max_iterations": int(row.max_iterations or 6),
        "description": row.description or "",
        "system_prompt": row.system_prompt or "",
        "duties": list(origin["duties"]) if origin else ["由主 Agent 按系统提示词按需调用"],
        "available_tools": clean_tool_names(loads(row.available_tools_json, [])),
        "skill_codes": loads(getattr(row, "skill_codes_json", None) or "[]", []),
        "model_config": normalize_model_config(loads(getattr(row, "model_config_json", None) or "{}", {})),
        "supports_stream": bool(row.supports_stream),
        "evaluation_spec": loads(getattr(row, "evaluation_spec_json", None) or "", None) or None,
        "timeout_seconds": int(getattr(row, "timeout_seconds", None) or 120),
    }


def _skill_out(row: OrchestrationSkill) -> dict:
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "description": row.description or "",
        "trigger_type": row.trigger_type,
        "trigger_value": row.trigger_value or "",
        "execution_type": row.execution_type,
        "entry_point": row.entry_point or "",
        "chainable": bool(row.chainable),
        "builtin": _builtin_skill_item(row.code) is not None,
        "persisted": True,
        "enabled": bool(getattr(row, "enabled", True)),
    }


async def list_catalog(db: AsyncSession, actor) -> dict:
    custom_agents = (
        await db.execute(
            apply_object_scope(select(AgentDefinition), AgentDefinition, actor).order_by(AgentDefinition.id.desc())
        )
    ).scalars().all()
    custom_skills = (
        await db.execute(
            apply_object_scope(select(OrchestrationSkill), OrchestrationSkill, actor).order_by(OrchestrationSkill.id.desc())
        )
    ).scalars().all()
    mcp_rows = (
        await db.execute(
            apply_object_scope(select(BaseResource).where(BaseResource.resource_type == "mcp"), BaseResource, actor)
        )
    ).scalars().all()
    agent_rows = {row.role: row for row in custom_agents}
    skill_rows = {row.code: row for row in custom_skills}
    subagents = []
    for item in BUILTIN_SUBAGENTS:
        row = agent_rows.pop(item["role"], None)
        subagents.append(_agent_out(row) if row is not None else _builtin_agent_out(item))
    subagents.extend(_agent_out(row) for row in agent_rows.values())
    skills = []
    for item in BUILTIN_SKILLS:
        row = skill_rows.pop(item["code"], None)
        skills.append(_skill_out(row) if row is not None else _builtin_skill_out(item))
    skills.extend(_skill_out(row) for row in skill_rows.values())
    return {
        "main_agent": {
            "role": "coordinator",
            "name": "测试任务管理主 Agent",
            "description": "用户唯一入口。统一理解目标、生成计划、跟踪执行、汇总子 Agent 结果。",
            "duties": ["需求理解", "任务配置与参数推荐", "编排与执行计划", "执行跟踪", "结果汇总与报告"],
        },
        "subagents": subagents,
        "skills": skills,
        "mcp_servers": [
            {
                "resource_id": row.resource_id,
                "name": row.name,
                "status": row.status,
                "health_status": row.health_status,
            }
            for row in mcp_rows
        ],
        "knowledge": {
            "role": "experience_store",
            "name": "经验知识库",
            "description": "历史模板、案例、异常策略和资源画像。不是独立 Agent。",
        },
    }


def _known_maps(catalog: dict) -> tuple[dict, dict, set[str]]:
    agents = {item["role"]: item for item in catalog["subagents"]}
    skills = {item["code"]: item for item in catalog["skills"]}
    mcps = {item["resource_id"] for item in catalog["mcp_servers"]}
    return agents, skills, mcps


async def normalize_capabilities(
    db: AsyncSession,
    actor,
    *,
    skill_codes: list[str] | None,
    mcp_resource_ids: list[str] | None,
    subagent_roles: list[str] | None,
) -> dict:
    catalog = await list_catalog(db, actor)
    agents, skills, mcps = _known_maps(catalog)
    roles: list[str] = []
    for role in list(REQUIRED_ROLES) + list(subagent_roles or []):
        spec = agents.get(role)
        if spec is None or spec.get("enabled") is False:
            raise HTTPException(400, f"未知子 Agent：{role}")
        if role not in roles:
            roles.append(role)
    chosen_skills: list[str] = []
    for code in skill_codes or []:
        spec = skills.get(code)
        if spec is None or spec.get("enabled") is False:
            raise HTTPException(400, f"未知编排 Skill：{code}")
        if code not in chosen_skills:
            chosen_skills.append(code)
    chosen_mcp: list[str] = []
    for rid in mcp_resource_ids or []:
        if rid not in mcps:
            raise HTTPException(400, f"未知或不可见 MCP：{rid}")
        if rid not in chosen_mcp:
            chosen_mcp.append(rid)
    return {
        "subagent_roles": roles,
        "skill_codes": chosen_skills,
        "mcp_resource_ids": chosen_mcp,
    }


async def create_definition(db: AsyncSession, actor, body: dict) -> AgentDefinition:
    role = (body.get("role") or "").strip()
    name = (body.get("name") or "").strip()
    if not ROLE_RE.match(role):
        raise HTTPException(400, "角色标识须为小写字母开头，仅含字母数字下划线")
    if any(item["role"] == role for item in BUILTIN_SUBAGENTS):
        raise HTTPException(400, "不能覆盖内置子 Agent")
    if not name:
        raise HTTPException(400, "请填写子 Agent 名称")
    exists = await db.scalar(
        select(AgentDefinition).where(
            AgentDefinition.role == role,
            or_(AgentDefinition.tenant_id == actor.tenant_id, AgentDefinition.tenant_id.is_(None)),
        )
    )
    if exists:
        raise HTTPException(400, "该角色已存在")
    catalog = await list_catalog(db, actor)
    row = AgentDefinition(
        role=role,
        name=name[:80],
        description=(body.get("description") or "")[:500],
        system_prompt=(body.get("system_prompt") or "")[:4000],
        max_iterations=max(1, min(int(body.get("max_iterations") or 10), 20)),
        supports_stream=bool(body.get("supports_stream")),
        human_in_the_loop=bool(body.get("human_in_the_loop")),
        available_tools_json=dumps(clean_tool_names(body.get("available_tools") if body.get("available_tools") is not None else ["search_knowledge"])),
        skill_codes_json=dumps(clean_skill_codes(body.get("skill_codes") or [], _known_skill_codes(catalog))),
        model_config_json=dumps(normalize_model_config(body.get("model_config"))),
        evaluation_spec_json=dumps(body.get("evaluation_spec")) if isinstance(body.get("evaluation_spec"), dict) else "",
        timeout_seconds=max(5, min(int(body.get("timeout_seconds") or 120), 600)),
        tenant_id=actor.tenant_id,
        creator_id=actor.user_id,
    )
    db.add(row)
    await db.flush()
    return row


async def create_skill(db: AsyncSession, actor, body: dict) -> OrchestrationSkill:
    code = (body.get("code") or "").strip()
    name = (body.get("name") or "").strip()
    trigger = "context"
    execution = (body.get("execution_type") or "prompt_template").strip()
    entry = (body.get("entry_point") or "").strip()
    if not SKILL_RE.match(code):
        raise HTTPException(400, "Skill 标识不合法")
    if any(item["code"] == code for item in BUILTIN_SKILLS):
        raise HTTPException(400, "不能覆盖内置编排 Skill")
    if trigger not in TRIGGER_TYPES:
        raise HTTPException(400, "触发类型不合法")
    if execution not in EXECUTION_TYPES:
        raise HTTPException(400, "执行方式不合法")
    if not name or not entry:
        raise HTTPException(400, "请填写名称和执行入口")
    exists = await db.scalar(select(OrchestrationSkill).where(OrchestrationSkill.code == code))
    if exists:
        raise HTTPException(400, "该 Skill 已存在")
    row = OrchestrationSkill(
        code=code,
        name=name[:80],
        description=(body.get("description") or "")[:500],
        trigger_type=trigger,
        trigger_value="",
        execution_type=execution,
        entry_point=entry[:4000],
        chainable=execution == "workflow",
        tenant_id=actor.tenant_id,
        creator_id=actor.user_id,
    )
    db.add(row)
    await db.flush()
    return row


def _known_skill_codes(catalog: dict) -> set[str]:
    return {item["code"] for item in catalog.get("skills") or [] if item.get("enabled") is not False}


async def _find_definition(db: AsyncSession, actor, role: str) -> AgentDefinition | None:
    return await db.scalar(
        select(AgentDefinition).where(
            AgentDefinition.role == role,
            or_(AgentDefinition.tenant_id == actor.tenant_id, AgentDefinition.tenant_id.is_(None)),
        )
    )


async def _find_skill(db: AsyncSession, actor, code: str) -> OrchestrationSkill | None:
    return await db.scalar(
        select(OrchestrationSkill).where(
            OrchestrationSkill.code == code,
            or_(OrchestrationSkill.tenant_id == actor.tenant_id, OrchestrationSkill.tenant_id.is_(None)),
        )
    )


def _fill_definition(row: AgentDefinition, body: dict, known_skills: set[str]) -> None:
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "请填写子 Agent 名称")
    row.name = name[:80]
    row.description = (body.get("description") or "")[:500]
    row.system_prompt = (body.get("system_prompt") or "")[:4000]
    row.max_iterations = max(1, min(int(body.get("max_iterations") or 10), 20))
    row.supports_stream = bool(body.get("supports_stream"))
    row.human_in_the_loop = bool(body.get("human_in_the_loop"))
    row.available_tools_json = dumps(clean_tool_names(body.get("available_tools") or []))
    row.skill_codes_json = dumps(clean_skill_codes(body.get("skill_codes") or [], known_skills))
    row.model_config_json = dumps(normalize_model_config(body.get("model_config")))
    spec = body.get("evaluation_spec")
    row.evaluation_spec_json = dumps(spec) if isinstance(spec, dict) else ""
    row.timeout_seconds = max(5, min(int(body.get("timeout_seconds") or 120), 600))
    if "enabled" in body:
        row.enabled = bool(body.get("enabled"))


async def update_definition(db: AsyncSession, actor, role: str, body: dict) -> dict:
    role = (role or "").strip()
    catalog = await list_catalog(db, actor)
    known = _known_skill_codes(catalog)
    row = await _find_definition(db, actor, role)
    origin = _builtin_agent_item(role)
    if row is None and origin is None:
        raise HTTPException(404, "子 Agent 不存在")
    if row is None:
        row = AgentDefinition(role=role, tenant_id=actor.tenant_id, creator_id=actor.user_id, builtin=False)
        db.add(row)
    if origin and origin["required"] and body.get("enabled") is False:
        raise HTTPException(400, "监控分析和异常诊断不能停用")
    _fill_definition(row, body, known)
    await db.flush()
    return _agent_out(row)


async def delete_definition(db: AsyncSession, actor, role: str) -> dict:
    role = (role or "").strip()
    origin = _builtin_agent_item(role)
    if origin and origin["required"]:
        raise HTTPException(400, "监控分析和异常诊断不能删除")
    row = await _find_definition(db, actor, role)
    if origin:
        if row is None:
            row = AgentDefinition(
                role=role,
                name=origin["name"],
                description=origin["description"],
                system_prompt=origin["description"],
                max_iterations=int(origin.get("max_iterations") or 6),
                human_in_the_loop=bool(origin.get("human_in_the_loop")),
                available_tools_json=dumps(["search_knowledge"]),
                skill_codes_json=dumps([]),
                enabled=False,
                tenant_id=actor.tenant_id,
                creator_id=actor.user_id,
            )
            db.add(row)
        else:
            row.enabled = False
        await db.flush()
        return _agent_out(row)
    if row is None:
        raise HTTPException(404, "子 Agent 不存在")
    await db.delete(row)
    await db.flush()
    return {"deleted": True, "role": role}


def _fill_skill(row: OrchestrationSkill, body: dict) -> None:
    name = (body.get("name") or "").strip()
    execution = (body.get("execution_type") or "prompt_template").strip()
    entry = (body.get("entry_point") or "").strip()
    if execution not in EXECUTION_TYPES:
        raise HTTPException(400, "执行方式不合法")
    if not name or not entry:
        raise HTTPException(400, "请填写名称和执行入口")
    row.name = name[:80]
    row.description = (body.get("description") or "")[:500]
    row.trigger_type = "context"
    row.trigger_value = ""
    row.execution_type = execution
    row.entry_point = entry[:4000]
    row.chainable = execution == "workflow"
    if "enabled" in body:
        row.enabled = bool(body.get("enabled"))


async def update_skill(db: AsyncSession, actor, code: str, body: dict) -> dict:
    code = (code or "").strip()
    row = await _find_skill(db, actor, code)
    origin = _builtin_skill_item(code)
    if row is None and origin is None:
        raise HTTPException(404, "编排 Skill 不存在")
    if row is None:
        row = OrchestrationSkill(code=code, tenant_id=actor.tenant_id, creator_id=actor.user_id, builtin=False)
        db.add(row)
    _fill_skill(row, body)
    await db.flush()
    return _skill_out(row)


async def delete_skill(db: AsyncSession, actor, code: str) -> dict:
    code = (code or "").strip()
    origin = _builtin_skill_item(code)
    row = await _find_skill(db, actor, code)
    if origin:
        if row is None:
            row = OrchestrationSkill(
                code=code,
                name=origin["name"],
                description=origin.get("description") or "",
                trigger_type="context",
                execution_type=origin.get("execution_type") or "prompt_template",
                entry_point=origin.get("entry_point") or "",
                chainable=origin.get("execution_type") == "workflow",
                enabled=False,
                tenant_id=actor.tenant_id,
                creator_id=actor.user_id,
            )
            db.add(row)
        else:
            row.enabled = False
        await db.flush()
        return _skill_out(row)
    if row is None:
        raise HTTPException(404, "编排 Skill 不存在")
    await db.delete(row)
    await db.flush()
    return {"deleted": True, "code": code}


def recipe_out(row: OrchestrationRecipe) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "requirement": row.requirement,
        "snapshot": loads(row.snapshot_json, {}),
        "source_session_id": row.source_session_id,
        "use_count": row.use_count,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def snapshot_from_plan(plan: dict, requirement: str) -> dict:
    caps = plan.get("capabilities") or {}
    return {
        "requirement": requirement,
        "token_budget": int(plan.get("token_budget") or 0),
        "scene": plan.get("scene") or "",
        "industry": plan.get("industry") or "",
        "dataset_id": plan.get("dataset_id"),
        "model_id": plan.get("model_id"),
        "judge_resource_id": plan.get("judge_resource_id") or "",
        "trial_run": bool(plan.get("trial_run")),
        "capabilities": {
            "subagent_roles": list(caps.get("subagent_roles") or list(REQUIRED_ROLES)),
            "skill_codes": list(caps.get("skill_codes") or []),
            "mcp_resource_ids": list(caps.get("mcp_resource_ids") or []),
        },
    }


async def save_recipe(db: AsyncSession, session: AgentSession, actor) -> OrchestrationRecipe:
    plan = loads(session.plan_json, {})
    snap = snapshot_from_plan(plan, session.requirement or "")
    row = await db.scalar(
        select(OrchestrationRecipe).where(OrchestrationRecipe.source_session_id == session.id)
    )
    if row is None:
        row = OrchestrationRecipe(
            title=(session.title or "编排经验")[:200],
            requirement=session.requirement or "",
            source_session_id=session.id,
            tenant_id=session.tenant_id,
            creator_id=getattr(actor, "user_id", None) or getattr(actor, "id", None),
        )
        db.add(row)
    row.title = (session.title or row.title or "编排经验")[:200]
    row.requirement = session.requirement or ""
    row.snapshot_json = dumps(snap)
    row.updated_at = datetime.utcnow()
    await db.flush()
    return row


async def list_recipes(db: AsyncSession, actor) -> list[OrchestrationRecipe]:
    q = apply_object_scope(select(OrchestrationRecipe), OrchestrationRecipe, actor)
    return (await db.execute(q.order_by(OrchestrationRecipe.id.desc()).limit(50))).scalars().all()


async def get_recipe(db: AsyncSession, recipe_id: int, actor) -> OrchestrationRecipe:
    row = await db.get(OrchestrationRecipe, recipe_id)
    if row is None or not object_is_visible(row, actor):
        raise HTTPException(404, "经验不存在或无权访问")
    return row


def _skill_by_code(catalog: dict, code: str) -> dict | None:
    for item in catalog["skills"]:
        if item["code"] == code:
            return item
    return None


def _agent_by_role(catalog: dict, role: str) -> dict | None:
    for item in catalog["subagents"]:
        if item["role"] == role:
            return item
    return None


async def execute_skill(db: AsyncSession, catalog: dict, code: str, text: str) -> dict:
    skill = _skill_by_code(catalog, code)
    if not skill:
        raise HTTPException(400, f"未知编排 Skill：{code}")
    kind = skill.get("execution_type")
    entry = skill.get("entry_point") or ""
    if kind == "prompt_template":
        return {
            "skill": code,
            "execution_type": kind,
            "instruction": entry,
            "input": text,
            "note": "这是给主 Agent 的提示约束，不是已完成的评测结果。",
        }
    if kind == "workflow" and entry == "knowledge.search":
        from app.services.agent_tools import search_knowledge

        items = await search_knowledge(db, text or skill.get("name") or code)
        return {"skill": code, "execution_type": kind, "items": items[:5], "count": len(items)}
    if kind == "agent":
        return {
            "skill": code,
            "execution_type": kind,
            "delegate_role": entry,
            "note": "请主 Agent 再调用对应子 Agent，Skill 本身不执行恢复。",
        }
    if kind == "code":
        raise HTTPException(400, "代码型编排 Skill 不在编排进程内执行，请改到工具底座注册")
    raise HTTPException(400, f"未实现的 Skill 执行方式：{kind}")


async def run_subagent(db: AsyncSession, session: AgentSession, actor, role: str) -> dict:
    plan = loads(session.plan_json, {})
    caps = plan.get("capabilities") or {}
    allowed = caps.get("subagent_roles") or list(REQUIRED_ROLES)
    if role not in allowed:
        raise HTTPException(400, "该子 Agent 未在本次编排中启用")
    catalog = await list_catalog(db, actor)
    spec = _agent_by_role(catalog, role)
    if spec is None:
        raise HTTPException(400, "未知子 Agent")

    delegation = AgentDelegation(
        session_id=session.id,
        run_id=session.active_run_id,
        role=role,
        depth=1,
        status="running",
        tenant_id=session.tenant_id,
        budget_slice=0,
    )
    db.add(delegation)
    await db.flush()

    task = await db.get(EvalTask, int(session.task_id)) if session.task_id else None
    timeout = int(spec.get("timeout_seconds") or 0)
    if timeout <= 0:
        profile = await get_main_profile(db, getattr(session, "tenant_id", None))
        timeout = int(profile.get("timeout_seconds") or 120)
    timeout = max(5, min(timeout, 600))

    async def _dispatch() -> dict:
        if role == "monitor":
            return await _monitor(db, session, task)
        if role == "diagnose":
            return await _diagnose(db, session, task)
        if role == "plan_analyst":
            return _plan_analysis(plan)
        if role == "report_reviewer":
            return _review_report(task)
        if role == "param_advisor":
            if "search_knowledge" in set(spec.get("available_tools") or []):
                return await _advise_params(db, plan, session.requirement or "")
            return {
                "status": "advised",
                "summary": "未授权检索经验知识，只根据当前计划给出建议。",
                "similar_cases": 0,
                "applies_change": False,
            }
        return await _custom_agent(db, spec, session.requirement or "")

    try:
        try:
            result = await asyncio.wait_for(_dispatch(), timeout=timeout)
            used = []
            for code in spec.get("skill_codes") or []:
                try:
                    used.append(await execute_skill(db, catalog, code, session.requirement or ""))
                except HTTPException as exc:
                    used.append({"skill": code, "error": str(exc.detail)})
            if used:
                result = {**result, "skills": used}
            result["available_tools"] = list(spec.get("available_tools") or [])
        except asyncio.TimeoutError as exc:
            delegation.status = "failed"
            delegation.finished_at = datetime.utcnow()
            await db.flush()
            raise HTTPException(504, f"子 Agent {role} 超时（{timeout}s），已终止并通知主 Agent") from exc
        delegation.status = "success" if result.get("status") != "unavailable" else "skipped"
        delegation.result_json = dumps(result)
        delegation.finished_at = datetime.utcnow()
        db.add(
            AgentMessage(
                session_id=session.id,
                role=role if role in {"monitor", "diagnose"} else "main",
                content=result.get("summary") or spec["name"],
                tool_name=f"delegate:{role}",
                payload_json=dumps({"role": role, "analysis_only": True}),
            )
        )
        await db.flush()
        return {"delegation_id": delegation.id, "role": role, "result": result}
    except HTTPException:
        delegation.status = "failed"
        delegation.finished_at = datetime.utcnow()
        await db.flush()
        raise


async def _monitor(db, session: AgentSession, task: EvalTask | None) -> dict:
    if task is None:
        return {
            "status": "waiting_task",
            "summary": "任务尚未创建。监控分析 Agent 会在任务提交后跟踪状态和进度。",
            "risk": "none",
        }
    from app.services.collaboration import run_collaborators

    out = await run_collaborators(db, session, force_roles=["monitor"])
    item = (out.get("items") or [{}])[0]
    report = item.get("result") or {}
    return {
        "status": "tracking",
        "summary": report.get("summary") or f"任务 #{task.id} 状态 {task.status}",
        "risk": report.get("risk") or "low",
        "report": report,
    }


async def _diagnose(db, session: AgentSession, task: EvalTask | None) -> dict:
    if task is None or task.status not in {"failed", "partial_failed", "paused_budget"}:
        return {
            "status": "no_failure",
            "summary": "当前没有失败或中断任务。异常诊断 Agent 不执行恢复。",
            "suggestions": [],
            "requires_main_approval": True,
        }
    from app.services.collaboration import run_collaborators

    out = await run_collaborators(db, session, force_roles=["diagnose"])
    item = (out.get("items") or [{}])[0]
    report = item.get("result") or {}
    report["requires_main_approval"] = True
    report.setdefault("summary", "诊断完成，恢复操作须回到主 Agent 并经确认。")
    return report


def _plan_analysis(plan: dict) -> dict:
    gaps = list(plan.get("resource_gaps") or [])
    errors = list(plan.get("validation_errors") or [])
    bits = []
    if gaps:
        bits.append("资源缺口：" + "；".join(str(g) for g in gaps))
    if errors:
        bits.append("校验：" + "；".join(str(e) for e in errors))
    if not bits:
        bits.append("当前计划未发现资源缺口。")
    bits.append("模式：" + ("试跑" if plan.get("trial_run") else "正式"))
    return {
        "status": "analyzed",
        "summary": " ".join(bits),
        "dataset_id": plan.get("dataset_id"),
        "model_id": plan.get("model_id"),
        "judge_resource_id": plan.get("judge_resource_id"),
        "creates_task": False,
    }


def _review_report(task: EvalTask | None) -> dict:
    if task is None:
        return {"status": "unavailable", "summary": "还没有任务结果，报告审校无本任务事实可核对。"}
    return {
        "status": "checked",
        "summary": (
            f"任务 #{task.id} 状态 {task.status}，通过 {task.success_count or 0}，"
            f"失败 {task.fail_count or 0}，进度 {task.progress or 0}。解释不得改这些数字。"
        ),
        "task_id": task.id,
        "success_count": task.success_count or 0,
        "fail_count": task.fail_count or 0,
        "mutates_score": False,
    }


async def _advise_params(db, plan: dict, requirement: str) -> dict:
    from app.services.agent_tools import search_knowledge

    hits = await search_knowledge(db, (requirement or "")[:40])
    advice = []
    if int(plan.get("token_budget") or 0) <= 0 and not plan.get("trial_run"):
        advice.append("正式评测需要正数 Token 预算，或改为试跑。")
    if plan.get("trial_run"):
        advice.append("当前为试跑，结论不能当作正式准入。")
    if plan.get("resource_gaps"):
        advice.append("先补齐资源缺口，再批准执行。")
    if not advice:
        advice.append("计划参数已齐，可进入审批。")
    return {
        "status": "advised",
        "summary": " ".join(advice),
        "similar_cases": len(hits),
        "applies_change": False,
    }


async def _custom_agent(db, spec: dict, requirement: str) -> dict:
    from app.services.agent_tools import search_knowledge

    tools = set(spec.get("available_tools") or [])
    hits = []
    if "search_knowledge" in tools:
        hits = await search_knowledge(db, (requirement or spec.get("name") or "")[:40])
    return {
        "status": "analyzed",
        "summary": spec.get("system_prompt") or spec.get("description") or spec["name"],
        "similar_cases": [{"id": item.get("id"), "title": item.get("title")} for item in hits[:3]],
        "executes_recovery": False,
    }
