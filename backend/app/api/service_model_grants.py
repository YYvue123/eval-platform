"""Explicit delivery of selected platform model snapshots to customer tenants."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.api.deps import require_permission
from app.api.service_customers import customer_for, record
from app.database import get_db
from app.models import EvalModel, ModelAccessConfig, ModelVersion, Tenant
from app.models.service_portal import ServiceModelGrant
from app.services.actor_context import build_actor
from app.services.model_access import assert_channel_allowed, get_access_for_version
from app.services.object_policy import apply_object_scope, get_visible_or_404

router = APIRouter()


class ModelGrantBody(BaseModel):
    model_id: int
    version_ids: list[int] = Field(min_length=1, max_length=20)


@router.get("/model-grant-options")
async def model_options(db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    from app.api.models import _acl_allows
    actor = await build_actor(db, current)
    rows = (await db.execute(apply_object_scope(select(EvalModel, ModelVersion), EvalModel, actor)
        .join(ModelVersion, ModelVersion.model_id == EvalModel.id)
        .join(ModelAccessConfig, (ModelAccessConfig.model_id == EvalModel.id) & (ModelAccessConfig.version_id == ModelVersion.id))
        .where(EvalModel.status.notin_(["deleted", "disabled", "archived"]),
               ModelVersion.status == "available", ModelAccessConfig.api_url != "")
        .order_by(EvalModel.id, ModelVersion.id))).all()
    models = {}
    for m, v in rows:
        if not await _acl_allows(db, m.id, current):
            continue
        models.setdefault(m.id, {"id": m.id, "name": m.name, "versions": []})["versions"].append(
            {"id": v.id, "version": v.version_code})
    return {"items": list(models.values())}


@router.get("/customers/{tid}/model-grants")
async def grants(tid: int, db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    await customer_for(db, tid)
    rows = (await db.execute(select(ServiceModelGrant, EvalModel.name, ModelVersion.version_code)
        .join(EvalModel, EvalModel.id == ServiceModelGrant.source_model_id)
        .join(ModelVersion, ModelVersion.id == ServiceModelGrant.source_version_id)
        .where(ServiceModelGrant.tenant_id == tid).order_by(ServiceModelGrant.id.desc()))).all()
    return {"items": [{"id": g.id, "name": name, "version": version, "active": g.active,
        "model_id": g.model_id, "version_id": g.version_id, "created_at": g.created_at.isoformat()}
        for g, name, version in rows]}


def live_config(cfg):
    auth = json.loads(cfg.auth_config or "{}")
    return {"api_url": cfg.api_url, "request_method": cfg.request_method, "auth_type": cfg.auth_type,
        "api_key": auth.get("api_key") or auth.get("token") or "", "served_model_name": auth.get("served_model_name") or "",
        "timeout": cfg.timeout, "retry_count": cfg.retry_count, "channel_type": cfg.channel_type,
        "request_template": cfg.request_template, "response_mapping": cfg.response_mapping,
        "parallel_limit": auth.get("parallel_limit") or 4}


@router.post("/customers/{tid}/model-grants")
async def grant_models(tid: int, body: ModelGrantBody, db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    from app.api.models import _acl_allows
    tenant = await customer_for(db, tid)
    # Serialize deliveries to keep repeated/concurrent requests idempotent.
    await db.execute(update(Tenant).where(Tenant.id == tid).values(status=Tenant.status))
    await db.refresh(tenant)
    if tenant.status != "active":
        raise HTTPException(409, "请先启用企业再授权模型")
    if tid == current.tenant_id:
        raise HTTPException(400, "请选择其他客户企业")
    actor = await build_actor(db, current)
    source = await get_visible_or_404(db, EvalModel, body.model_id, actor)
    if source.status in {"deleted", "disabled", "archived"} or not await _acl_allows(db, source.id, current):
        raise HTTPException(400, "模型不可用或没有模型调用授权")
    snapshots = []
    for vid in dict.fromkeys(body.version_ids):
        v = await db.get(ModelVersion, vid)
        cfg = await get_access_for_version(db, source.id, vid)
        if not v or v.model_id != source.id or v.status != "available" or not cfg or not cfg.api_url:
            raise HTTPException(400, "请选择该模型可用且具有冻结接口配置的版本")
        try:
            assert_channel_allowed(cfg.channel_type)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        snapshots.append((v, cfg))
    existing = (await db.scalars(select(ServiceModelGrant).where(
        ServiceModelGrant.tenant_id == tid, ServiceModelGrant.source_model_id == source.id))).all()
    target = await db.get(EvalModel, existing[0].model_id) if existing else None
    if not target:
        target = EvalModel(name=source.name, model_type=source.model_type, description=source.description,
            support_language=source.support_language, support_modal=source.support_modal,
            scene_white_list=source.scene_white_list, tenant_id=tid, creator_id=current.id,
            visibility="shared", status="active")
        db.add(target)
        await db.flush()
    ids = []
    for version, cfg in snapshots:
        grant = next((g for g in existing if g.source_version_id == version.id), None)
        if grant:
            if grant.active:
                ids.append(grant.id)
                continue
            grant.active = True
            target_version = await db.get(ModelVersion, grant.version_id)
            target_version.status = "available"
        else:
            target_version = ModelVersion(model_id=target.id, version_code=version.version_code,
                version_desc=f"平台授权快照：{source.name} / {version.version_code}", creator_id=current.id)
            db.add(target_version)
            await db.flush()
            config = {c.key: getattr(cfg, c.key) for c in cfg.__table__.columns if c.key not in {"id", "model_id", "version_id"}}
            db.add(ModelAccessConfig(**config, model_id=target.id, version_id=target_version.id))
            grant = ServiceModelGrant(tenant_id=tid, source_model_id=source.id, source_version_id=version.id,
                model_id=target.id, version_id=target_version.id, creator_id=current.id)
            db.add(grant)
            await db.flush()
        target.status = "active"
        target.current_version_id, target.current_version = target_version.id, target_version.version_code
        for key, value in live_config(cfg).items():
            setattr(target, key, value)
        await record(db, current, tid, "model_grant", grant.id,
            f"授权模型：{source.name}；冻结版本：{version.version_code}")
        ids.append(grant.id)
    return {"ids": ids, "model_id": target.id}


@router.delete("/customers/{tid}/model-grants/{gid}")
async def revoke_grant(tid: int, gid: int, db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    await customer_for(db, tid)
    await db.execute(update(Tenant).where(Tenant.id == tid).values(status=Tenant.status))
    grant = await db.scalar(select(ServiceModelGrant).where(ServiceModelGrant.id == gid, ServiceModelGrant.tenant_id == tid))
    if not grant:
        raise HTTPException(404, "模型授权不存在")
    if grant.active:
        grant.active = False
        version = await db.get(ModelVersion, grant.version_id)
        version.status = "disabled"
        remaining = await db.scalar(select(ServiceModelGrant.id).where(
            ServiceModelGrant.model_id == grant.model_id, ServiceModelGrant.active.is_(True)))
        if not remaining:
            model = await db.get(EvalModel, grant.model_id)
            model.status = "disabled"
        await record(db, current, tid, "model_revoke", gid, f"撤销模型授权；版本：{version.version_code}")
    return {"id": gid, "active": False}
