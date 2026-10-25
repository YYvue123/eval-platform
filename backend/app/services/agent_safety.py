"""Safety plans use the same protocol and authorization gates as manual tasks."""
from fastapi import HTTPException
from sqlalchemy import select

from app.models import Dataset, DatasetItem, DatasetVersion, EvalModel, User
from app.services.object_policy import get_visible_or_404
from app.services.safety_protocol import SafetyConfig, sample_of, validate_sample


async def prepare_safety_plan(db, plan, actor, *, freeze=False):
    raw = plan.get("safety_config")
    if not raw:
        if plan.get("judge_resource_id") == "builtin/safety_protocol" or plan.get("task_type") == "security":
            raise ValueError("安全评测必须配置安全协议、指标权重与追问策略")
        return None
    if actor is None or not (actor.is_admin or actor.has_permission("safety:create")):
        raise HTTPException(403, "需要权限: safety:create")
    from app.api.models import _acl_allows
    config = SafetyConfig.model_validate(raw)
    ds = await get_visible_or_404(db, Dataset, plan.get("dataset_id"), actor)
    model = await get_visible_or_404(db, EvalModel, plan.get("model_id"), actor)
    version_id = plan.get("dataset_version_id") or ds.current_version_id
    version = await db.get(DatasetVersion, version_id) if version_id else None
    if not version or version.dataset_id != ds.id:
        raise ValueError("安全基准版本不属于所选数据集")
    items = (await db.scalars(select(DatasetItem).where(DatasetItem.version_id == version_id, DatasetItem.status == "active"))).all()
    if not items:
        raise ValueError("安全基准不能为空")
    from app.services.multimodal import validate_plan_media, validate_compatibility
    from app.services.model_access import model_call_view, get_access_for_version
    plan["media_summary"] = await validate_plan_media(db, plan)
    dimensions = {validate_sample(sample_of(item)) for item in items}
    if any(weight > 0 and code not in dimensions for code, weight in config.dimension_weights.items()):
        raise ValueError("基准未覆盖所有正权重指标，请调整基准或指标权重")
    if config.judge_model_id:
        judge = await get_visible_or_404(db, EvalModel, config.judge_model_id, actor)
        user = await db.get(User, actor.user_id)
        if judge.status in {"deleted", "disabled", "archived"} or not judge.api_url or not await _acl_allows(db, judge.id, user):
            raise HTTPException(403, "安全裁判模型不可调用")
        view = model_call_view(judge, await get_access_for_version(db, judge.id, judge.current_version_id if freeze else config.judge_version_id))
        for item in items:
            validate_compatibility(view, item, judge=True)
        if freeze:
            config.judge_version_id = judge.current_version_id
        elif config.judge_version_id != judge.current_version_id:
            raise ValueError("裁判模型版本已变化，请更新计划并重新审批")
    result = config.model_dump()
    if freeze:
        plan.update(safety_config=result, task_type="security", judge_resource_id="builtin/safety_protocol",
                    template_code="", dataset_version_id=version_id, metric_weights=config.dimension_weights)
    return result
