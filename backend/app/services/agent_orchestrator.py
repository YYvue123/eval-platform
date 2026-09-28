"""主 Agent 编排：GoalSpec + 资源硬过滤 + 澄清；执行必须审批后走工具。"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dataset, EvalModel
from app.services.agent_tools import retrieve_templates, search_knowledge, validate_eval_config
from app.services.goal_spec import build_goal_spec, clarification_gaps, canonical_plan_hash
from app.services.task_catalog import INDUSTRIES, SCENES, find_template
from app.utils.jsonutil import loads


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
    if any_ds and industry == "general" and scene in {"chat", "qa", ""}:
        return any_ds, gaps
    if not any_ds:
        gaps.append("无可用数据集")
    else:
        gaps.append(f"无匹配 scene={scene}/industry={industry} 的数据集（拒绝使用无关最新资源 #{any_ds.id}）")
    return None, gaps


async def _pick_model(db: AsyncSession, scene: str, industry: str) -> tuple[EvalModel | None, list[str]]:
    gaps: list[str] = []
    q = select(EvalModel).where(EvalModel.status.notin_(["deleted", "disabled", "archived"]))
    rows = (await db.execute(q.order_by(EvalModel.id.desc()).limit(30))).scalars().all()
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

    if ov.get("model_id"):
        model = await db.get(EvalModel, int(ov["model_id"]))
        if not model or model.status in {"deleted", "disabled", "archived"}:
            model = None
            resource_gaps.append("指定模型不可用")
    else:
        model, g2 = await _pick_model(db, scene, industry)
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
