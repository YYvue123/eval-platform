"""主 Agent 编排：规则理解需求 → 知识优化 → 计划；执行必须确认后走工具。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dataset, EvalModel
from app.services.agent_tools import retrieve_templates, search_knowledge, validate_eval_config
from app.services.task_catalog import INDUSTRIES, SCENES, find_template


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


async def draft_plan(db: AsyncSession, requirement: str, user) -> dict:
    scene, industry = infer_dims(requirement)
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
    ds = (await db.execute(
        select(Dataset).where(Dataset.status != "deleted").order_by(Dataset.id.desc()).limit(1)
    )).scalar_one_or_none()
    model = (await db.execute(
        select(EvalModel).where(EvalModel.status.notin_(["deleted", "disabled", "archived"])).order_by(EvalModel.id.desc()).limit(1)
    )).scalar_one_or_none()
    trial = False
    if ds and ds.quality_status in {"failed", "check_failed"}:
        trial = True
    plan = {
        "name": f"编排:{requirement[:40]}",
        "requirement": requirement,
        "scene": tpl.get("scene") or scene,
        "industry": tpl.get("industry") or industry,
        "task_type": tpl.get("task_type") or "capability",
        "template_code": code,
        "judge_resource_id": tpl.get("judge_resource_id") or "builtin/exact_match",
        "dataset_id": ds.id if ds else None,
        "model_id": model.id if model else None,
        "trial_run": trial,
        "need_confirm": True,
    }
    errors = await validate_eval_config(db, plan, user)
    plan["validation_errors"] = errors
    plan["knowledge"] = knowledge[:5]
    plan["templates"] = tpls
    plan["ready"] = not errors and bool(plan["dataset_id"] and plan["model_id"])
    return plan
