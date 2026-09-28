"""被测模型管理。"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission, require_actor
from app.database import get_db
from app.models import (
    EvalModel,
    EvalTask,
    ModelAccessConfig,
    ModelAcl,
    ModelCallLog,
    ModelHealthSample,
    ModelMeta,
    ModelVersion,
    User,
)
from app.services.actor_context import ActorContext, effective_tenant_id
from app.services.audit import get_client_ip, log_audit
from app.services.health_probe import record_probe
from app.services.model_client import health_check, invoke_model
from app.services.model_access import ACCESS_FIELD_NAMES, assert_channel_allowed, bump_version_and_freeze, insert_access_snapshot
from app.services.object_policy import apply_object_scope, get_visible_or_404
from app.services.model_access import ACCESS_FIELD_NAMES, bump_version_and_freeze, insert_access_snapshot
from app.services.serializers import model_out
from app.utils.jsonutil import dumps, iso, loads

router = APIRouter()

META_FIELDS = (
    "train_data_desc", "finetune_method", "infer_framework", "hardware",
    "company_name", "company_model_code", "contact_name", "contact_email",
    "source_type", "base_model", "deploy_cluster", "industry",
)


class ModelCreate(BaseModel):
    name: str
    model_type: str = "llm"
    model_source: str = "external"
    description: str = ""
    support_language: str = "zh"
    support_modal: str = "text"
    deploy_type: str = "api"
    access_mode: str = "online"
    architecture: str = ""
    parameter_scale: str = ""
    context_length: int = 8192
    applicable_scenario: str = ""
    current_version: str = "V1.0"
    api_url: str = ""
    request_method: str = "POST"
    auth_type: str = "bearer_token"
    api_key: str = ""
    served_model_name: str = ""
    timeout: int = 60
    retry_count: int = 1
    channel_type: str = "https"
    request_template: str = ""
    response_mapping: str = ""
    scene_white_list: list[str] = Field(default_factory=list)
    parallel_limit: int = 4
    support_stream: bool = False
    probe_interval_sec: int = 300
    status: str = "draft"
    train_data_desc: str = ""
    finetune_method: str = ""
    infer_framework: str = ""
    hardware: str = ""
    company_name: str = ""
    company_model_code: str = ""
    contact_name: str = ""
    contact_email: str = ""
    source_type: str = ""
    base_model: str = ""
    deploy_cluster: str = ""
    industry: str = ""


class ModelUpdate(BaseModel):
    name: str | None = None
    model_type: str | None = None
    model_source: str | None = None
    description: str | None = None
    support_language: str | None = None
    support_modal: str | None = None
    deploy_type: str | None = None
    access_mode: str | None = None
    architecture: str | None = None
    parameter_scale: str | None = None
    context_length: int | None = None
    applicable_scenario: str | None = None
    current_version: str | None = None
    api_url: str | None = None
    request_method: str | None = None
    auth_type: str | None = None
    api_key: str | None = None
    served_model_name: str | None = None
    timeout: int | None = None
    retry_count: int | None = None
    channel_type: str | None = None
    request_template: str | None = None
    response_mapping: str | None = None
    scene_white_list: list[str] | None = None
    parallel_limit: int | None = None
    support_stream: bool | None = None
    probe_interval_sec: int | None = None
    status: str | None = None
    train_data_desc: str | None = None
    finetune_method: str | None = None
    infer_framework: str | None = None
    hardware: str | None = None
    company_name: str | None = None
    company_model_code: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    source_type: str | None = None
    base_model: str | None = None
    deploy_cluster: str | None = None
    industry: str | None = None


class InvokeBody(BaseModel):
    prompt: str
    scene: str = ""


class VersionCreate(BaseModel):
    version_code: str
    version_desc: str = ""


class AclCreate(BaseModel):
    principal_type: str = "user"
    principal_id: int
    action: str = "invoke"
    allow: bool = True


def _split_payload(data: dict) -> tuple[dict, dict]:
    meta = {k: data.pop(k) for k in list(data) if k in META_FIELDS}
    return data, meta


async def _get_meta(db: AsyncSession, model_id: int) -> ModelMeta | None:
    return (await db.execute(select(ModelMeta).where(ModelMeta.model_id == model_id))).scalar_one_or_none()


async def _upsert_meta(db: AsyncSession, model_id: int, meta: dict) -> ModelMeta:
    row = await _get_meta(db, model_id)
    if not row:
        row = ModelMeta(model_id=model_id)
        db.add(row)
        await db.flush()
    for k, v in meta.items():
        setattr(row, k, v)
    return row


async def _sync_access(db: AsyncSession, m: EvalModel) -> None:
    """仅为当前版本补齐不可变快照，绝不覆盖已有行。"""
    await insert_access_snapshot(db, m)


async def _ensure_version(db: AsyncSession, m: EvalModel, user_id: int | None) -> ModelVersion:
    if m.current_version_id:
        ver = await db.get(ModelVersion, m.current_version_id)
        if ver:
            return ver
    ver = ModelVersion(model_id=m.id, version_code=m.current_version or "V1.0", version_desc="初始版本", creator_id=user_id)
    db.add(ver)
    await db.flush()
    m.current_version_id = ver.id
    m.current_version = ver.version_code
    return ver


async def _acl_allows(db: AsyncSession, model_id: int, user: User) -> bool:
    if getattr(user, "role", None) == "admin":
        return True
    rows = (await db.execute(select(ModelAcl).where(ModelAcl.model_id == model_id, ModelAcl.action == "invoke"))).scalars().all()
    if not rows:
        return True
    allowed = False
    for row in rows:
        match = (row.principal_type == "user" and row.principal_id == user.id) or (
            row.principal_type == "role" and row.principal_id == (user.role_id or 0)
        )
        if not match:
            continue
        if row.allow:
            allowed = True
        else:
            return False
    return allowed


@router.get("")
async def list_models(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    search: str = Query(""),
    status: str = Query(""),
    model_source: str = Query(""),
    support_modal: str = Query(""),
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("model:list")),
):
    q = select(EvalModel).where(EvalModel.status != "deleted")
    q = apply_object_scope(q, EvalModel, actor)
    if search:
        q = q.where(or_(EvalModel.name.contains(search), EvalModel.description.contains(search)))
    if status:
        q = q.where(EvalModel.status == status)
    if model_source:
        q = q.where(EvalModel.model_source == model_source)
    if support_modal:
        q = q.where(EvalModel.support_modal == support_modal)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(EvalModel.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [model_out(m) for m in rows], "total": total or 0}


@router.post("")
async def create_model(
    body: ModelCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("model:create")),
):
    data = body.model_dump()
    data, meta = _split_payload(data)
    scenes = data.pop("scene_white_list", []) or []
    claimed = data.pop("tenant_id", None) if "tenant_id" in data else None
    m = EvalModel(
        **data,
        scene_white_list=dumps(scenes),
        creator_id=actor.user_id,
        tenant_id=effective_tenant_id(actor, claimed),
        visibility="private",
    )
    db.add(m)
    await db.flush()
    await _ensure_version(db, m, actor.user_id)
    await _upsert_meta(db, m.id, meta)
    try:
        await _sync_access(db, m)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await log_audit(db, "model", "create", user_id=actor.user_id, username=actor.username, target_id=m.id, ip=get_client_ip(request))
    return model_out(m, meta=await _get_meta(db, m.id))


@router.get("/{model_id}")
async def get_model(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("model:view")),
):
    m = await get_visible_or_404(db, EvalModel, model_id, actor, not_found="模型不存在或无权访问")
    if m.status == "deleted":
        raise HTTPException(404, "模型不存在或无权访问")
    logs = (await db.execute(select(ModelCallLog).where(ModelCallLog.model_id == model_id).order_by(ModelCallLog.id.desc()).limit(50))).scalars().all()
    versions = (await db.execute(select(ModelVersion).where(ModelVersion.model_id == model_id).order_by(ModelVersion.id.desc()))).scalars().all()
    acls = (await db.execute(select(ModelAcl).where(ModelAcl.model_id == model_id).order_by(ModelAcl.id.desc()))).scalars().all()
    samples = (await db.execute(select(ModelHealthSample).where(ModelHealthSample.model_id == model_id).order_by(ModelHealthSample.id.desc()).limit(30))).scalars().all()
    used = (await db.scalar(select(func.count()).select_from(EvalTask).where(EvalTask.model_id == model_id))) or 0
    return {
        **model_out(m, meta=await _get_meta(db, model_id)),
        "in_use": used,
        "versions": [
            {"id": v.id, "version_code": v.version_code, "version_desc": v.version_desc, "status": v.status, "created_at": iso(v.created_at)}
            for v in versions
        ],
        "acls": [
            {"id": a.id, "principal_type": a.principal_type, "principal_id": a.principal_id, "action": a.action, "allow": bool(a.allow)}
            for a in acls
        ],
        "health_samples": [
            {"id": s.id, "ok": bool(s.ok), "status": s.status, "latency_ms": s.latency_ms, "detail": s.detail, "created_at": iso(s.created_at)}
            for s in samples
        ],
        "logs": [
            {
                "id": lg.id,
                "call_status": lg.call_status,
                "latency_ms": lg.latency_ms,
                "token_usage": lg.token_usage,
                "error_message": lg.error_message,
                "created_at": iso(lg.created_at),
            }
            for lg in logs
        ],
    }


@router.put("/{model_id}")
async def update_model(
    model_id: int,
    body: ModelUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("model:edit")),
):
    m = await db.get(EvalModel, model_id)
    if not m or m.status == "deleted":
        raise HTTPException(404, "模型不存在")
    data = body.model_dump(exclude_unset=True)
    if data.get("api_key") == "":
        data.pop("api_key")
    if "scene_white_list" in data:
        m.scene_white_list = dumps(data.pop("scene_white_list") or [])
    data, meta = _split_payload(data)
    if data.get("status") in {"published", "deleted"}:
        raise HTTPException(400, "不允许直接修改为该状态")
    access_changed = any(k in data for k in ACCESS_FIELD_NAMES)
    for k, v in data.items():
        setattr(m, k, v)
    if meta:
        await _upsert_meta(db, m.id, meta)
    try:
        if access_changed:
            # 访问配置变更 → 新版本 + 新快照，旧 ModelAccessConfig 保持不变
            await bump_version_and_freeze(db, m, current.id, desc="访问配置变更")
        else:
            await _ensure_version(db, m, current.id)
            await _sync_access(db, m)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await log_audit(db, "model", "update", user_id=current.id, username=current.username, target_id=m.id, ip=get_client_ip(request))
    return model_out(m, meta=await _get_meta(db, m.id))


@router.delete("/{model_id}")
async def delete_model(
    model_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("model:delete")),
):
    m = await db.get(EvalModel, model_id)
    if not m or m.status == "deleted":
        raise HTTPException(404, "模型不存在")
    used = (await db.scalar(select(func.count()).select_from(EvalTask).where(EvalTask.model_id == model_id))) or 0
    m.status = "deleted"
    await log_audit(db, "model", "delete", user_id=current.id, username=current.username, target_id=model_id, ip=get_client_ip(request))
    return {"ok": True, "logical": True, "task_count": used}


@router.post("/{model_id}/versions")
async def create_version(
    model_id: int,
    body: VersionCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("model:edit")),
):
    m = await db.get(EvalModel, model_id)
    if not m or m.status == "deleted":
        raise HTTPException(404, "模型不存在")
    exists = await db.scalar(select(ModelVersion.id).where(ModelVersion.model_id == model_id, ModelVersion.version_code == body.version_code))
    if exists:
        raise HTTPException(400, "版本号已存在")
    ver = ModelVersion(model_id=model_id, version_code=body.version_code, version_desc=body.version_desc, creator_id=current.id)
    db.add(ver)
    await db.flush()
    return {"id": ver.id, "version_code": ver.version_code}


@router.post("/{model_id}/versions/{version_id}/activate")
async def activate_version(
    model_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("model:edit")),
):
    m = await db.get(EvalModel, model_id)
    ver = await db.get(ModelVersion, version_id)
    if not m or not ver or ver.model_id != model_id:
        raise HTTPException(404, "版本不存在")
    m.current_version_id = ver.id
    m.current_version = ver.version_code
    # 激活历史版本：若该版本已有冻结配置则不覆盖；否则用当前 live 字段补齐一次
    try:
        await _sync_access(db, m)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    cfg = await db.scalar(
        select(ModelAccessConfig).where(
            ModelAccessConfig.model_id == m.id,
            ModelAccessConfig.version_id == ver.id,
        )
    )
    if cfg:
        # 将 live 指针字段对齐到已冻结配置，便于 UI 展示（不改历史 cfg）
        auth = loads(cfg.auth_config or "{}", {}) or {}
        m.api_url = cfg.api_url
        m.request_method = cfg.request_method
        m.auth_type = cfg.auth_type
        m.request_template = cfg.request_template or ""
        m.response_mapping = cfg.response_mapping or ""
        m.timeout = cfg.timeout
        m.retry_count = cfg.retry_count
        m.channel_type = cfg.channel_type
        if auth.get("api_key"):
            m.api_key = auth["api_key"]
        if auth.get("served_model_name"):
            m.served_model_name = auth["served_model_name"]
    return model_out(m)


@router.post("/{model_id}/acl")
async def add_acl(
    model_id: int,
    body: AclCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("model:edit")),
):
    m = await db.get(EvalModel, model_id)
    if not m or m.status == "deleted":
        raise HTTPException(404, "模型不存在")
    row = ModelAcl(
        model_id=model_id,
        principal_type=body.principal_type,
        principal_id=body.principal_id,
        action=body.action,
        allow=body.allow,
    )
    db.add(row)
    await db.flush()
    return {"id": row.id}


@router.delete("/{model_id}/acl/{acl_id}")
async def delete_acl(
    model_id: int,
    acl_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("model:edit")),
):
    row = await db.get(ModelAcl, acl_id)
    if not row or row.model_id != model_id:
        raise HTTPException(404, "ACL 不存在")
    await db.delete(row)
    return {"ok": True}


@router.post("/{model_id}/health")
async def check_model_health(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("model:view")),
):
    m = await db.get(EvalModel, model_id)
    if not m or m.status == "deleted":
        raise HTTPException(404, "模型不存在")
    result = await health_check(m)
    await record_probe(m, result, db)
    return {**result, "health_status": m.health_status}


@router.post("/{model_id}/invoke")
async def invoke(
    model_id: int,
    body: InvokeBody,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("model:invoke")),
):
    m = await db.get(EvalModel, model_id)
    if not m or m.status == "deleted":
        raise HTTPException(404, "模型不存在")
    if m.status in {"disabled", "archived"}:
        raise HTTPException(400, "模型已停用或归档")
    if not await _acl_allows(db, model_id, current):
        raise HTTPException(403, "没有该模型的调用权限")
    whitelist = loads(m.scene_white_list or "[]", [])
    if body.scene and whitelist and body.scene not in whitelist:
        raise HTTPException(400, f"场景 {body.scene} 不在模型白名单中")
    try:
        result = await invoke_model(m, body.prompt)
        db.add(ModelCallLog(model_id=m.id, user_id=current.id, call_status="success", latency_ms=result["latency_ms"], token_usage=result["tokens"]))
        return result
    except Exception as exc:
        db.add(ModelCallLog(model_id=m.id, user_id=current.id, call_status="failed", error_message=str(exc)[:2000]))
        raise HTTPException(400, f"调用失败: {exc}") from exc
