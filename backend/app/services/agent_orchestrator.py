"""主 Agent 编排：GoalSpec + 资源硬过滤 + 澄清；执行必须审批后走工具。"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dataset, EvalModel
from app.services.agent_tools import retrieve_templates, search_knowledge, validate_eval_config
from app.services.goal_spec import build_goal_spec, clarification_gaps, canonical_plan_hash
from app.services.task_catalog import INDUSTRIES, SCENES, find_template
from app.utils.jsonutil import dumps, loads


def infer_dims(text: str) -> tuple[str, str]:
    raw = text or ""
    industry = "general"
    scene = "chat"
    for code, name in INDUSTRIES:
        if code in raw or name in raw:
            industry = code
            break
    for code, name in SCENES:
        if code in raw or name in raw:
            scene = code
            break
    if "安全" in raw or "幻觉" in raw or "水印" in raw:
        scene = "chat"
    return scene, industry


async def _pick_dataset(db: AsyncSession, scene: str, industry: str) -> tuple[Dataset | None, list[str]]:
    """硬过滤：优先 industry/scene 匹配，禁止随意取「最新无关」资源冒充。"""
    gaps: list[str] = []
    q = select(Dataset).where(Dataset.status != "deleted")
    preferred = None
    if industry and industry != "general":
        preferred = (
            await db.execute(
                q.where(or_(Dataset.domain_type == industry, Dataset.tags.contains(industry))).order_by(Dataset.id.desc()).limit(1)
            )
        ).scalar_one_or_none()
    if not preferred and scene:
        preferred = (
            await db.execute(
                q.where(or_(Dataset.task_type.contains(scene), Dataset.tags.contains(scene), Dataset.name.contains(scene))).order_by(Dataset.id.desc()).limit(1)
            )
        ).scalar_one_or_none()
    if preferred:
        return preferred, gaps
    # 无匹配：不回退到任意最新；记 gap（试验包可再放宽）
    any_ds = (await db.execute(q.order_by(Dataset.id.desc()).limit(1))).scalar_one_or_none()
    if not any_ds:
        gaps.append("无可用数据集")
    else:
        gaps.append(f"无匹配 scene={scene}/industry={industry} 的数据集（拒绝使用无关最新资源 #{any_ds.id}）")
    return None, gaps


def _is_planner_model(model: EvalModel) -> bool:
    name = (model.name or "").lower()
    return "planner" in name or "规划" in (model.name or "")


async def _pick_model(
    db: AsyncSession,
    scene: str,
    industry: str,
    *,
    exclude_ids: set[int] | None = None,
) -> tuple[EvalModel | None, list[str]]:
    gaps: list[str] = []
    blocked = exclude_ids or set()
    q = select(EvalModel).where(EvalModel.status.notin_(["deleted", "disabled", "archived"]))
    rows = [
        m for m in (await db.execute(q.order_by(EvalModel.id.desc()).limit(30))).scalars().all()
        if m.id not in blocked and not _is_planner_model(m)
    ]
    matched = []
    for m in rows:
        wl = loads(m.scene_white_list or "[]", []) or []
        if wl and scene not in wl:
            continue
        meta_hit = industry == "general" or industry in (m.applicable_scenario or "") or industry in (m.name or "")
        scene_hit = not wl or scene in wl or scene in (m.applicable_scenario or "")
        if meta_hit and scene_hit:
            matched.append(m)
    if matched:
        return matched[0], gaps
    if not rows:
        gaps.append("无可用被测模型")
        return None, gaps
    # 无白名单限制的模型可作为 general 回退
    open_models = [m for m in rows if not loads(m.scene_white_list or "[]", [])]
    if open_models and industry == "general":
        return open_models[0], gaps
    gaps.append(f"无匹配 scene={scene} 的模型（拒绝无关最新模型）")
    return None, gaps


async def draft_plan(
    db: AsyncSession,
    requirement: str,
    user,
    *,
    token_budget: int = 0,
    objective: str = "",
    overrides: dict | None = None,
) -> dict:
    scene, industry = infer_dims(requirement)
    ov = overrides or {}
    if ov.get("scene"):
        scene = ov["scene"]
    if ov.get("industry"):
        industry = ov["industry"]

    knowledge = await search_knowledge(db, requirement[:40])
    tpls = await retrieve_templates(db, scene=scene, industry=industry)
    code = ""
    if "幻觉" in requirement:
        code = "safety.hallucination"
    elif "水印" in requirement or "标识" in requirement:
        code = "safety.watermark"
    elif industry != "general":
        code = f"industry.{industry}"
    elif tpls:
        code = tpls[0]["code"]
    else:
        code = f"scene.{scene}"
    tpl = find_template(code) or {}

    resource_gaps: list[str] = []
    if ov.get("dataset_id"):
        ds = await db.get(Dataset, int(ov["dataset_id"]))
        if not ds or ds.status == "deleted":
            ds = None
            resource_gaps.append("指定数据集不可用")
    else:
        ds, g1 = await _pick_dataset(db, scene, industry)
        resource_gaps.extend(g1)

    exclude = set()
    for item in ov.get("exclude_model_ids") or []:
        try:
            exclude.add(int(item))
        except (TypeError, ValueError):
            continue
    if ov.get("model_id"):
        model = await db.get(EvalModel, int(ov["model_id"]))
        if not model or model.status in {"deleted", "disabled", "archived"}:
            model = None
            resource_gaps.append("指定模型不可用")
        elif _is_planner_model(model) or model.id in exclude:
            model = None
            resource_gaps.append("规划模型不能作为被测模型")
    else:
        model, g2 = await _pick_model(db, scene, industry, exclude_ids=exclude)
        resource_gaps.extend(g2)

    trial = bool(ov.get("trial_run")) if "trial_run" in ov else False
    if ds and ds.quality_status in {"failed", "check_failed", "unchecked", "checking", "needs_clean"}:
        trial = True
    if ds and ds.status != "published":
        trial = True
    if model and not (model.api_url or "").strip():
        trial = True

    budget = int(ov.get("token_budget") if ov.get("token_budget") is not None else token_budget or 0)
    goal = build_goal_spec(
        requirement=requirement,
        scene=tpl.get("scene") or scene,
        industry=tpl.get("industry") or industry,
        objective=objective or ov.get("objective") or "",
        token_budget=budget,
    )

    plan = {
        "name": f"编排:{requirement[:40]}",
        "requirement": requirement,
        "scene": tpl.get("scene") or scene,
        "industry": tpl.get("industry") or industry,
        "task_type": tpl.get("task_type") or "capability",
        "template_code": code,
        "judge_resource_id": tpl.get("judge_resource_id") or "builtin/exact_match",
        "dataset_id": ds.id if ds else None,
        "dataset_version_id": ds.current_version_id if ds else None,
        "model_id": model.id if model else None,
        "model_version_id": model.current_version_id if model else None,
        "trial_run": trial,
        "token_budget": budget,
        "need_confirm": True,
        "resource_gaps": resource_gaps,
        "goal_spec": goal,
    }
    plan["clarifications"] = clarification_gaps(goal, plan)
    errors = await validate_eval_config(db, plan, user)
    plan["validation_errors"] = errors
    plan["knowledge"] = knowledge[:5]
    plan["templates"] = tpls
    plan["canonical_hash"] = canonical_plan_hash(plan)
    plan["ready"] = (
        not errors
        and not plan["clarifications"]
        and bool(plan["dataset_id"] and plan["model_id"])
        and not resource_gaps
    )
    # 有澄清但资源齐：仍可 waiting_confirm 若仅缺 budget 且 trial
    if not plan["ready"] and not errors and plan["dataset_id"] and plan["model_id"] and trial:
        only_budget = plan["clarifications"] and all(c.get("field") == "token_budget" for c in plan["clarifications"])
        if only_budget:
            plan["ready"] = True
            plan["clarifications"] = [c for c in plan["clarifications"] if c.get("field") != "token_budget"]
    return plan


async def search_eval_resources(db: AsyncSession, query: str, kind: str = "") -> dict:
    """给主 Agent 检索可写入计划的数据集、被测模型和打分工具。规划模型不出现在模型列表。"""
    text = (query or "").strip()
    out: dict = {"datasets": [], "models": [], "judges": []}
    if kind in {"", "dataset"}:
        q = select(Dataset).where(Dataset.status != "deleted")
        if text:
            q = q.where(or_(Dataset.name.contains(text), Dataset.tags.contains(text), Dataset.task_type.contains(text)))
        rows = (await db.execute(q.order_by(Dataset.id.desc()).limit(8))).scalars().all()
        out["datasets"] = [{"id": row.id, "name": row.name, "task_type": row.task_type, "status": row.status} for row in rows]
    if kind in {"", "model"}:
        q = select(EvalModel).where(EvalModel.status.notin_(["deleted", "disabled", "archived"]))
        if text:
            q = q.where(or_(EvalModel.name.contains(text), EvalModel.applicable_scenario.contains(text)))
        rows = (await db.execute(q.order_by(EvalModel.id.desc()).limit(12))).scalars().all()
        out["models"] = [
            {"id": row.id, "name": row.name, "applicable_scenario": row.applicable_scenario or ""}
            for row in rows
            if not _is_planner_model(row)
        ][:8]
    if kind in {"", "judge"}:
        from app.models import BaseResource, ResourceEvent
        from app.services.judge_options import mcp_judge_id

        q = select(BaseResource).where(BaseResource.resource_type.in_(["tool", "skill", "mcp"]))
        rows = (await db.execute(q.order_by(BaseResource.id.asc()).limit(40))).scalars().all()
        judges = []
        for row in rows:
            if row.resource_type != "mcp":
                if text and text not in (row.name or "") and text not in (row.resource_id or ""):
                    continue
                judges.append({"resource_id": row.resource_id, "name": row.name, "resource_type": row.resource_type})
                continue
            catalog = await db.scalar(
                select(ResourceEvent)
                .where(ResourceEvent.resource_id == row.resource_id, ResourceEvent.event_type == "mcp.catalog")
                .order_by(ResourceEvent.id.desc())
            )
            payload = loads(catalog.payload_json, {}) if catalog else {}
            tools = payload.get("tools") if isinstance(payload.get("tools"), list) else []
            if not tools:
                tools = [{"name": name} for name in (payload.get("tool_names") or [])]
            for tool in tools:
                if not isinstance(tool, dict) or not tool.get("name"):
                    continue
                tool_name = str(tool["name"])
                if text and text not in tool_name and text not in (row.name or "") and text not in (row.resource_id or ""):
                    continue
                judges.append({
                    "resource_id": mcp_judge_id(row.resource_id, tool_name),
                    "name": f"{row.name} / {tool_name}",
                    "resource_type": "mcp",
                })
        out["judges"] = judges[:12]
    return out


async def apply_resource_proposal(db: AsyncSession, session, args: dict) -> dict:
    """把对话里确认的数据集、被测模型和打分工具写进计划。规划模型不能当被测模型。"""
    from app.models import BaseResource
    from app.services.approval_service import invalidate_if_plan_changed
    from app.services.goal_spec import canonical_plan_hash

    plan = loads(session.plan_json, {})
    changed = []
    if args.get("dataset_id") not in (None, ""):
        ds = await db.get(Dataset, int(args["dataset_id"]))
        if not ds or ds.status == "deleted":
            raise ValueError("dataset_not_found")
        plan["dataset_id"] = ds.id
        plan["dataset_version_id"] = ds.current_version_id
        changed.append(f"数据集 {ds.name}")
    if args.get("model_id") not in (None, ""):
        model = await db.get(EvalModel, int(args["model_id"]))
        if not model or model.status in {"deleted", "disabled", "archived"}:
            raise ValueError("model_not_found")
        if _is_planner_model(model) or int(model.id) == int(session.planner_model_id or 0):
            raise ValueError("planner_cannot_be_target")
        plan["model_id"] = model.id
        plan["model_version_id"] = model.current_version_id
        changed.append(f"被测模型 {model.name}")
    if args.get("judge_resource_id"):
        from app.services.judge_options import parse_mcp_judge

        judge_id = str(args["judge_resource_id"]).strip()
        parsed = parse_mcp_judge(judge_id)
        if parsed:
            parent, tool_name = parsed
            res = await db.scalar(select(BaseResource).where(BaseResource.resource_id == parent))
            if res is None or res.resource_type != "mcp":
                raise ValueError("judge_not_found")
            label = f"{res.name}/{tool_name}"
        else:
            res = await db.scalar(select(BaseResource).where(BaseResource.resource_id == judge_id))
            if res is None or res.resource_type not in {"tool", "skill"}:
                raise ValueError("judge_not_found")
            label = res.name
        plan["judge_resource_id"] = judge_id
        changed.append(f"打分工具 {label}")
    if args.get("scene"):
        plan["scene"] = str(args["scene"])[:40]
        changed.append(f"场景 {plan['scene']}")
    if not changed:
        raise ValueError("proposal_empty")
    from app.services.agent_tools import validate_eval_config
    from app.services.goal_spec import clarification_gaps

    kept_gaps = []
    for gap in plan.get("resource_gaps") or []:
        if plan.get("dataset_id") and "数据" in gap:
            continue
        if plan.get("model_id") and "模型" in gap:
            continue
        kept_gaps.append(gap)
    plan["resource_gaps"] = kept_gaps
    plan["validation_errors"] = await validate_eval_config(db, plan, None)
    plan["clarifications"] = clarification_gaps(plan.get("goal_spec") or {}, plan)
    plan["canonical_hash"] = canonical_plan_hash(plan)
    plan["dialogue_updated"] = True
    plan["ready"] = (
        not plan["validation_errors"]
        and not plan["clarifications"]
        and bool(plan.get("dataset_id") and plan.get("model_id"))
        and not plan["resource_gaps"]
    )
    if session.status in {"planning", "waiting_confirm"}:
        session.status = "waiting_confirm" if plan["ready"] else "planning"
    await invalidate_if_plan_changed(db, session.id, plan)
    session.plan_json = dumps(plan)
    return {"updated": changed, "dataset_id": plan.get("dataset_id"), "model_id": plan.get("model_id"), "judge_resource_id": plan.get("judge_resource_id")}
