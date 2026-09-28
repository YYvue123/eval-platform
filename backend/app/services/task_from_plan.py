"""从审批计划创建任务：统一门禁与 ACL，供 Agent confirm 复用。"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.models import _acl_allows
from app.models import Dataset, EvalModel, EvalTask, User
from app.services.task_events import emit_event
from app.utils.jsonutil import dumps, loads


async def create_task_from_plan(
    db: AsyncSession,
    plan: dict,
    user: User,
    *,
    tenant_id: int | None = None,
) -> EvalTask:
    ds_id = plan.get("dataset_id")
    model_id = plan.get("model_id")
    ds = await db.get(Dataset, ds_id) if ds_id else None
    model = await db.get(EvalModel, model_id) if model_id else None
    if not ds or ds.status == "deleted":
        raise HTTPException(400, "数据集不可用")
    if not model or model.status in {"deleted", "disabled", "archived"}:
        raise HTTPException(400, "被测模型不可用")
    trial = bool(plan.get("trial_run"))
    if not trial:
        if ds.status != "published":
            raise HTTPException(400, "正式评测要求数据集已发布")
        if ds.quality_status in {"unchecked", "failed", "check_failed", "checking", "needs_clean"}:
            raise HTTPException(400, "正式评测要求质检通过")
        if not (model.api_url or "").strip():
            raise HTTPException(400, "正式执行拒绝无 endpoint 模型")
    if not await _acl_allows(db, model.id, user):
        raise HTTPException(403, "没有该模型的调用权限")
    whitelist = loads(model.scene_white_list or "[]", [])
    scene = plan.get("scene") or "chat"
    if whitelist and scene not in whitelist:
        raise HTTPException(400, f"场景 {scene} 不在模型白名单中")

    t = EvalTask(
        name=plan.get("name") or "编排任务",
        task_type=plan.get("task_type") or "capability",
        scene=scene,
        industry=plan.get("industry") or "general",
        dataset_id=ds.id,
        dataset_version_id=plan.get("dataset_version_id") or ds.current_version_id,
        model_id=model.id,
        model_version_id=plan.get("model_version_id") or model.current_version_id,
        judge_resource_id=plan.get("judge_resource_id") or "builtin/exact_match",
        template_code=plan.get("template_code") or "",
        trial_run=trial,
        token_quota=int(plan.get("token_budget") or 0),
        creator_id=user.id,
        tenant_id=tenant_id if tenant_id is not None else getattr(user, "tenant_id", None),
        visibility="private",
        metric_weights_json=dumps(plan.get("metric_weights") or {}),
    )
    db.add(t)
    await db.flush()
    await emit_event(db, t.id, "created", {"via": "agent_approval", "plan_hash": plan.get("canonical_hash")})
    return t
