"""External customer portal and a narrowly scoped API-key evaluation gateway."""
from hashlib import sha256
import json
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.api.deps import require_permission, get_current_user
from app.database import get_db, async_session
from app.models import (Dataset, DatasetVersion, DatasetItem, EvalModel, EvalServiceRequest, EvalTask, EvalWorkspace,
                        ModelVersion, ServiceCall, ServiceClient, ServiceRelease, ServiceRoute,
                        Tenant, TenantMembership, User, ServiceGatewayAudit)
from app.services.actor_context import build_actor
from app.services.audit import log_audit
from app.services.model_access import get_access_for_version
from app.services.object_policy import apply_object_scope, get_visible_or_404
from app.services.service_portal import (call_out, check_admission, choose_release,
                                         client_usage, workspace_for)
from app.utils.auth import get_password_hash

class AuditedGatewayRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def audited(request):
            code = 500
            try:
                response = await handler(request)
                code = response.status_code
                return response
            except Exception as exc:
                code = getattr(exc, "status_code", 422 if exc.__class__.__name__ == "RequestValidationError" else 500)
                raise
            finally:
                async with async_session() as db:
                    digest = sha256(request.headers.get("x-api-key", "").encode()).hexdigest()
                    client = await db.scalar(select(ServiceClient).where(ServiceClient.key_hash == digest))
                    db.add(ServiceGatewayAudit(tenant_id=client.tenant_id if client else 0,
                        client_id=client.id if client else None, method=request.method,
                        path=request.url.path[:240], status_code=code))
                    await db.commit()
        return audited


async def active_tenant(db=Depends(get_db), current=Depends(get_current_user)):
    tenant = await db.get(Tenant, current.tenant_id)
    if not tenant or tenant.status != "active":
        raise HTTPException(403, "企业已停用或不存在")


router = APIRouter(dependencies=[Depends(active_tenant)])
gateway = APIRouter(route_class=AuditedGatewayRoute)


class WorkspaceBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ClientBody(BaseModel):
    workspace_id: int
    name: str = Field(min_length=1, max_length=120)


class QuotaBody(BaseModel):
    daily_tokens: int = Field(ge=0, le=2_000_000_000)
    monthly_tokens: int = Field(ge=0, le=2_000_000_000)
    requests_per_minute: int = Field(ge=1, le=1000)
    price_fen_per_1k: int = Field(ge=0, le=1000000)


class RouteBody(BaseModel):
    workspace_id: int
    name: str = Field(min_length=1, max_length=120)


class ReleaseBody(BaseModel):
    version: str = Field(min_length=1, max_length=40)
    model_id: int
    model_version_id: int


class TrafficBody(BaseModel):
    stable_id: int
    candidate_id: int | None = None
    gray_percent: int = Field(default=0, ge=0, le=100)


class EvaluationBody(BaseModel):
    client_id: int
    route_id: int
    title: str = Field(min_length=1, max_length=200)
    requirement: str = Field(default="", max_length=10000)
    mode: Literal["auto", "expert"] = "auto"
    dataset_id: int
    token_budget: int = Field(gt=0, le=100000000)
    scene: str = Field(default="qa", max_length=80)
    judge_resource_id: Literal["builtin/exact_match", "builtin/contains", "builtin/regex", "builtin/fuzzy"] = "builtin/exact_match"
    metric_weights: dict[str, float] = Field(default_factory=dict)


class MemberBody(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)


async def owned(db, model, rid, current):
    row = await db.scalar(select(model).where(model.id == rid, model.tenant_id == current.tenant_id))
    if not row:
        raise HTTPException(404, "资源不存在或无权访问")
    return row


@router.get("/workspaces")
async def workspaces(db=Depends(get_db), current=Depends(require_permission("service:list"))):
    rows = (await db.scalars(select(EvalWorkspace).where(EvalWorkspace.tenant_id == current.tenant_id))).all()
    return {"items": [{"id": w.id, "name": w.name, "code": w.code} for w in rows]}


@router.post("/workspaces")
async def create_workspace(body: WorkspaceBody, db=Depends(get_db), current=Depends(require_permission("service:workspace"))):
    w = EvalWorkspace(name=body.name, code=secrets.token_hex(12), tenant_id=current.tenant_id,
                      owner_id=current.id, visibility="shared")
    db.add(w)
    await db.flush()
    return {"id": w.id, "name": w.name}


@router.get("/members")
async def members(db=Depends(get_db), current=Depends(require_permission("service:list"))):
    rows = (await db.scalars(select(User).where(User.tenant_id == current.tenant_id))).all()
    return {"items": [{"id": u.id, "username": u.username, "status": u.status} for u in rows]}


@router.post("/members")
async def create_member(body: MemberBody, db=Depends(get_db), current=Depends(require_permission("service:workspace"))):
    if await db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(409, "用户名不可用")
    u = User(username=body.username, password_hash=get_password_hash(body.password),
             role="customer", tenant_id=current.tenant_id, created_by=current.id)
    db.add(u)
    await db.flush()
    db.add(TenantMembership(tenant_id=current.tenant_id, user_id=u.id))
    await log_audit(db, "service", "member_create", user_id=current.id, target_id=u.id)
    return {"id": u.id, "username": u.username}


class CustomerBody(MemberBody):
    company: str = Field(min_length=1, max_length=120)


@router.post("/customers")
async def onboard_customer(body: CustomerBody, db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    if await db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(409, "用户名不可用")
    tenant = Tenant(code="customer-" + secrets.token_hex(10), name=body.company)
    db.add(tenant)
    await db.flush()
    user = User(username=body.username, password_hash=get_password_hash(body.password),
                role="customer", tenant_id=tenant.id, created_by=current.id)
    db.add(user)
    await db.flush()
    db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id))
    ws = EvalWorkspace(name=body.company, code=secrets.token_hex(12), tenant_id=tenant.id, owner_id=user.id)
    db.add(ws)
    await db.flush()
    await log_audit(db, "service", "customer_create", user_id=current.id, target_id=user.id)
    return {"user_id": user.id, "tenant_id": tenant.id, "workspace_id": ws.id}


@router.get("/clients")
async def clients(workspace_id: int, db=Depends(get_db), current=Depends(require_permission("service:list"))):
    await workspace_for(db, workspace_id, current.tenant_id)
    rows = (await db.scalars(select(ServiceClient).where(ServiceClient.workspace_id == workspace_id))).all()
    return {"items": [{"id": c.id, "name": c.name, "key_prefix": c.key_prefix, "active": c.active,
                       "daily_tokens": c.daily_tokens, "monthly_tokens": c.monthly_tokens,
                       "requests_per_minute": c.requests_per_minute, "price_fen_per_1k": c.price_fen_per_1k,
                       "usage": await client_usage(db, c)} for c in rows]}


@router.post("/clients")
async def create_client(body: ClientBody, db=Depends(get_db), current=Depends(require_permission("service:credential"))):
    await workspace_for(db, body.workspace_id, current.tenant_id)
    key = "evs_" + secrets.token_urlsafe(32)
    c = ServiceClient(**body.model_dump(), tenant_id=current.tenant_id, creator_id=current.id,
                      key_hash=sha256(key.encode()).hexdigest(), key_prefix=key[:12],
                      daily_tokens=0, monthly_tokens=0)
    db.add(c)
    await db.flush()
    await log_audit(db, "service", "client_create", user_id=current.id, target_id=c.id)
    return {"id": c.id, "api_key": key, "message": "密钥仅展示一次；额度需由服务运营分配"}


@router.post("/clients/{cid}/revoke")
async def revoke_client(cid: int, db=Depends(get_db), current=Depends(require_permission("service:credential"))):
    c = await owned(db, ServiceClient, cid, current)
    c.active = False
    await log_audit(db, "service", "client_revoke", user_id=current.id, target_id=c.id)
    return {"active": False}


@router.put("/clients/{cid}/quota")
async def set_quota(cid: int, body: QuotaBody, db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    # Service operators explicitly administer customer contracts across tenants.
    c = await db.get(ServiceClient, cid)
    if not c:
        raise HTTPException(404, "接入方不存在")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    await log_audit(db, "service", "quota", user_id=current.id, target_id=c.id, detail=json.dumps(body.model_dump()))
    return {"id": c.id, **body.model_dump()}


@router.get("/assets")
async def assets(db=Depends(get_db), current=Depends(require_permission("service:list"))):
    actor = await build_actor(db, current)
    datasets = (await db.scalars(apply_object_scope(select(Dataset), Dataset, actor).where(Dataset.status == "published", Dataset.visibility == "shared"))).all()
    models = (await db.scalars(apply_object_scope(select(EvalModel), EvalModel, actor).where(EvalModel.status.notin_(["deleted", "disabled", "archived"]), EvalModel.visibility == "shared"))).all()
    versions = (await db.scalars(select(ModelVersion).where(ModelVersion.model_id.in_([m.id for m in models])))).all()
    return {"datasets": [{"id": d.id, "name": d.name} for d in datasets],
            "models": [{"id": m.id, "name": m.name} for m in models],
            "versions": [{"id": v.id, "model_id": v.model_id, "version": v.version_code} for v in versions]}


class AssetGrantBody(BaseModel):
    tenant_id: int
    dataset_id: int


@router.post("/assets/grants")
async def grant_dataset(body: AssetGrantBody, db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    """Deliver a copy of a measured, published dataset snapshot to a customer tenant."""
    tenant = await db.get(Tenant, body.tenant_id)
    if not tenant or tenant.status != "active":
        raise HTTPException(404, "客户企业不存在或已停用")
    actor = await build_actor(db, current)
    source = await get_visible_or_404(db, Dataset, body.dataset_id, actor)
    version = await db.get(DatasetVersion, source.current_version_id) if source.current_version_id else None
    if source.status != "published" or source.quality_status != "passed" or not version:
        raise HTTPException(400, "只能交付已有质检通过证据的已发布数据集版本")
    items = (await db.scalars(select(DatasetItem).where(DatasetItem.dataset_id == source.id,
                                                       DatasetItem.version_id == version.id))).all()
    if not items:
        raise HTTPException(400, "数据集版本没有样本")
    def copy_columns(row, omit):
        return {c.key: getattr(row, c.key) for c in row.__table__.columns if c.key not in omit}
    ds = Dataset(**copy_columns(source, {"id", "tenant_id", "creator_id", "visibility", "current_version_id", "created_at", "updated_at"}),
                 tenant_id=tenant.id, creator_id=current.id, visibility="shared")
    db.add(ds)
    await db.flush()
    snapshot = DatasetVersion(**copy_columns(version, {"id", "dataset_id", "file_path", "creator_id", "created_at"}),
                              dataset_id=ds.id, creator_id=current.id)
    db.add(snapshot)
    await db.flush()
    ds.current_version_id = snapshot.id
    for item in items:
        db.add(DatasetItem(**copy_columns(item, {"id", "dataset_id", "version_id", "created_at", "updated_at"}),
                           dataset_id=ds.id, version_id=snapshot.id))
    await log_audit(db, "service", "asset_grant", user_id=current.id, target_id=ds.id,
                    tenant_id=str(tenant.id), detail=f"source_dataset={source.id};source_version={version.id}")
    return {"dataset_id": ds.id, "version_id": snapshot.id, "tenant_id": tenant.id}


@router.get("/routes")
async def routes(workspace_id: int, db=Depends(get_db), current=Depends(require_permission("service:list"))):
    await workspace_for(db, workspace_id, current.tenant_id)
    rows = (await db.scalars(select(ServiceRoute).where(ServiceRoute.workspace_id == workspace_id))).all()
    result = []
    for row in rows:
        versions = (await db.scalars(select(ServiceRelease).where(ServiceRelease.route_id == row.id))).all()
        result.append({"id": row.id, "name": row.name, "stable_id": row.stable_id,
                       "candidate_id": row.candidate_id, "gray_percent": row.gray_percent,
                       "previous_id": row.previous_id,
                       "versions": [{"id": v.id, "version": v.version, "model_id": v.model_id,
                                     "model_version_id": v.model_version_id} for v in versions]})
    return {"items": result}


@router.post("/routes")
async def register_route(body: RouteBody, db=Depends(get_db), current=Depends(require_permission("service:publish"))):
    await workspace_for(db, body.workspace_id, current.tenant_id)
    if await db.scalar(select(ServiceRoute.id).where(ServiceRoute.workspace_id == body.workspace_id, ServiceRoute.name == body.name)):
        raise HTTPException(409, "该工作空间已注册同名模型服务")
    row = ServiceRoute(**body.model_dump(), tenant_id=current.tenant_id)
    db.add(row)
    await db.flush()
    return {"id": row.id}


@router.post("/routes/{rid}/versions")
async def add_release(rid: int, body: ReleaseBody, db=Depends(get_db), current=Depends(require_permission("service:publish"))):
    await owned(db, ServiceRoute, rid, current)
    actor = await build_actor(db, current)
    model = await get_visible_or_404(db, EvalModel, body.model_id, actor)
    version = await db.get(ModelVersion, body.model_version_id)
    cfg = await get_access_for_version(db, model.id, body.model_version_id)
    if not version or version.model_id != model.id or version.status != "available" or not cfg or not cfg.api_url:
        raise HTTPException(400, "版本必须属于所选模型且具有可用的冻结接口配置")
    # Tenant-shared assets are required so every customer workspace member can execute.
    if model.visibility != "shared":
        raise HTTPException(400, "请先将模型设为企业共享资产")
    if await db.scalar(select(ServiceRelease.id).where(ServiceRelease.route_id == rid, ServiceRelease.version == body.version)):
        raise HTTPException(409, "服务版本已存在，版本映射不可覆盖")
    row = ServiceRelease(route_id=rid, **body.model_dump())
    db.add(row)
    await db.flush()
    await log_audit(db, "service", "version_register", user_id=current.id, target_id=rid)
    return {"id": row.id}


class EndpointBody(BaseModel):
    version: str = Field(min_length=1, max_length=40)
    api_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=500)
    served_model_name: str = Field(min_length=1, max_length=200)


@router.post("/routes/{rid}/endpoints")
async def register_endpoint(rid: int, body: EndpointBody, request: Request, db=Depends(get_db), current=Depends(require_permission("service:publish"))):
    from urllib.parse import urlsplit
    from app.config import settings
    from app.api.models import ModelCreate, create_model
    route = await owned(db, ServiceRoute, rid, current)
    try:
        url = urlsplit(body.api_url)
        port = url.port
    except ValueError as exc:
        raise HTTPException(400, "模型接口地址无效") from exc
    allowed = {h.strip().lower() for h in settings.SERVICE_MODEL_HOSTS.split(",") if h.strip()}
    if url.scheme != "https" or not url.hostname or url.hostname.lower() not in allowed or url.username or url.password or url.fragment or url.query or port not in (None, 443):
        raise HTTPException(400, "模型接口须使用运营允许域名的 HTTPS 地址（443 端口）；请联系运营配置 SERVICE_MODEL_HOSTS")
    if await db.scalar(select(ServiceRelease.id).where(ServiceRelease.route_id == rid, ServiceRelease.version == body.version)):
        raise HTTPException(409, "该服务版本已注册")
    actor = await build_actor(db, current)
    data = await create_model(ModelCreate(name=f"{route.name}/{body.version}", api_url=body.api_url,
        api_key=body.api_key, served_model_name=body.served_model_name, current_version=body.version,
        status="active"), request, db, actor)
    model = await db.get(EvalModel, data["id"])
    model.visibility = "shared"
    release = ServiceRelease(route_id=rid, version=body.version, model_id=model.id, model_version_id=model.current_version_id)
    db.add(release)
    await db.flush()
    # Never echo upstream credentials/configuration in the customer response.
    return {"id": release.id, "version": release.version}


@router.put("/routes/{rid}/traffic")
async def traffic(rid: int, body: TrafficBody, db=Depends(get_db), current=Depends(require_permission("service:publish"))):
    row = await owned(db, ServiceRoute, rid, current)
    for vid in [body.stable_id, body.candidate_id]:
        if vid:
            version = await db.get(ServiceRelease, vid)
            if not version or version.route_id != row.id:
                raise HTTPException(400, "版本不属于当前模型服务")
    if body.gray_percent and (not body.candidate_id or body.candidate_id == body.stable_id):
        raise HTTPException(400, "灰度版本必须与稳定版本不同")
    if row.stable_id != body.stable_id:
        row.previous_id = row.stable_id
    row.stable_id, row.candidate_id, row.gray_percent = body.stable_id, body.candidate_id, body.gray_percent
    await log_audit(db, "service", "traffic", user_id=current.id, target_id=rid, detail=json.dumps(body.model_dump()))
    return {"id": rid}


@router.post("/routes/{rid}/rollback")
async def rollback(rid: int, db=Depends(get_db), current=Depends(require_permission("service:publish"))):
    row = await owned(db, ServiceRoute, rid, current)
    if not row.previous_id:
        raise HTTPException(409, "没有可回滚的稳定版本")
    row.stable_id, row.previous_id = row.previous_id, row.stable_id
    row.candidate_id, row.gray_percent = None, 0
    await log_audit(db, "service", "rollback", user_id=current.id, target_id=rid)
    return {"id": rid}


async def evaluate(body, request, db, current, idem, bound_client=None):
    if not idem or len(idem) > 100:
        raise HTTPException(400, "需要 1–100 字符的 Idempotency-Key")
    client = await owned(db, ServiceClient, body.client_id, current)
    if bound_client is not None and client.id != bound_client:
        raise HTTPException(403, "API Key 不属于所选接入方")
    # Serialize admission per client across processes (SQLite write lock / SQL row lock).
    await db.execute(update(ServiceClient).where(ServiceClient.id == client.id).values(active=ServiceClient.active))
    await db.refresh(client)
    if not client.active:
        raise HTTPException(401, "接入方密钥已撤销")
    digest = sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
    prior = await db.scalar(select(ServiceCall).where(ServiceCall.client_id == client.id, ServiceCall.idempotency_key == idem))
    if prior:
        if prior.request_hash != digest:
            raise HTTPException(409, "幂等键已用于不同请求")
        return await call_out(db, prior)
    route = await owned(db, ServiceRoute, body.route_id, current)
    if route.workspace_id != client.workspace_id:
        raise HTTPException(404, "模型服务不属于接入方工作空间")
    release = await db.get(ServiceRelease, choose_release(route, f"{client.id}:{idem}")) if route.stable_id else None
    if not release:
        raise HTTPException(400, "模型服务尚未配置稳定版本")
    await check_admission(db, client, body.token_budget)
    actor = await build_actor(db, current)
    ds = await get_visible_or_404(db, Dataset, body.dataset_id, actor)
    if ds.visibility != "shared":
        raise HTTPException(400, "请选择企业共享的已发布数据集")
    if not ds.current_version_id or not await db.scalar(select(DatasetItem.id).where(
            DatasetItem.dataset_id == ds.id, DatasetItem.version_id == ds.current_version_id).limit(1)):
        raise HTTPException(400, "数据集必须有已发布版本和评测样本")
    cfg = await get_access_for_version(db, release.model_id, release.model_version_id)
    version = await db.get(ModelVersion, release.model_version_id)
    if not cfg or not cfg.api_url or not version or version.status != "available":
        raise HTTPException(400, "冻结模型配置不可用")
    from app.api.tasks import TaskCreate, create_task
    task_data = await create_task(TaskCreate(name=body.title, dataset_id=body.dataset_id,
        model_id=release.model_id, model_version_id=release.model_version_id,
        token_quota=body.token_budget, scene=body.scene,
        judge_resource_id=body.judge_resource_id if body.mode == "expert" else "builtin/exact_match",
        metric_weights=body.metric_weights if body.mode == "expert" else {}), request, db, actor)
    task = await db.get(EvalTask, task_data["id"])
    service = EvalServiceRequest(title=body.title, requirement=body.requirement, quote_mode=body.mode,
        workspace_id=client.workspace_id, tenant_id=current.tenant_id, creator_id=current.id,
        dataset_id=body.dataset_id, model_id=release.model_id, task_id=task.id,
        status="configuring" if body.mode == "expert" else "running", visibility="shared")
    db.add(service)
    await db.flush()
    call = ServiceCall(tenant_id=current.tenant_id, workspace_id=client.workspace_id, client_id=client.id,
        service_id=service.id, release_id=release.id, task_id=task.id, idempotency_key=idem,
        request_hash=digest, reserved_tokens=body.token_budget, price_fen_per_1k=client.price_fen_per_1k)
    db.add(call)
    if body.mode == "auto":
        from app.services.task_service import enqueue_task
        await enqueue_task(db, task)
    await db.flush()
    return await call_out(db, call)


async def audited_evaluate(body, request, db, current, idem, bound_client=None):
    try:
        result = await evaluate(body, request, db, current, idem, bound_client)
        await db.commit()
        return result
    except HTTPException as exc:
        tenant_id = current.tenant_id
        await db.rollback()
        client = await db.scalar(select(ServiceClient).where(ServiceClient.id == body.client_id, ServiceClient.tenant_id == tenant_id))
        db.add(ServiceCall(tenant_id=tenant_id, client_id=client.id if client else None,
            workspace_id=client.workspace_id if client else None, status="rejected", detail=str(exc.detail)))
        await db.commit()
        raise


@router.post("/evaluations")
async def submit_evaluation(body: EvaluationBody, request: Request, idempotency_key: str = Header(...),
                            db=Depends(get_db), current=Depends(require_permission("service:create"))):
    return await audited_evaluate(body, request, db, current, idempotency_key)


@router.get("/evaluations")
async def evaluations(workspace_id: int, page: int = Query(1, ge=1), db=Depends(get_db), current=Depends(require_permission("service:list"))):
    await workspace_for(db, workspace_id, current.tenant_id)
    rows = (await db.scalars(select(ServiceCall).where(ServiceCall.workspace_id == workspace_id)
        .order_by(ServiceCall.id.desc()).offset((page - 1) * 50).limit(50))).all()
    items = []
    for c in rows:
        data = await call_out(db, c)
        service = await db.get(EvalServiceRequest, c.service_id) if c.service_id else None
        data.update(title=service.title if service else "调用被拒绝", mode=service.quote_mode if service else "—")
        items.append(data)
    return {"items": items, "page": page}


@router.post("/evaluations/{cid}/start")
async def start_expert(cid: int, db=Depends(get_db), current=Depends(require_permission("service:run"))):
    call = await owned(db, ServiceCall, cid, current)
    client = await owned(db, ServiceClient, call.client_id, current)
    await db.execute(update(ServiceClient).where(ServiceClient.id == client.id).values(active=ServiceClient.active))
    await db.refresh(client)
    if not client.active:
        raise HTTPException(403, "接入方已撤销")
    task = await db.get(EvalTask, call.task_id) if call.task_id else None
    if task:
        await db.refresh(task)
    if not task or task.status != "draft":
        raise HTTPException(409, "仅待确认的专家配置可启动")
    await check_admission(db, client, 0)
    from app.services.task_service import enqueue_task
    await enqueue_task(db, task)
    await log_audit(db, "service", "start", user_id=current.id, target_id=call.id)
    return await call_out(db, call)


@router.post("/evaluations/{cid}/cancel")
async def cancel(cid: int, db=Depends(get_db), current=Depends(require_permission("service:run"))):
    call = await owned(db, ServiceCall, cid, current)
    task = await db.get(EvalTask, call.task_id) if call.task_id else None
    if not task:
        raise HTTPException(404, "任务不存在")
    from app.services.task_service import request_cancel
    await request_cancel(db, task)
    await log_audit(db, "service", "cancel", user_id=current.id, target_id=call.id)
    return await call_out(db, call)


async def download_report(db, call):
    data = await call_out(db, call)
    if not data["report_ready"]:
        raise HTTPException(409, "正式报告尚未生成")
    from app.services.report_archive import report_file
    path = report_file(call.task_id, "json")
    if not path.is_file():
        raise HTTPException(404, "报告文件不存在")
    return FileResponse(path, filename=f"evaluation-{call.id}.json", media_type="application/json")


@router.get("/evaluations/{cid}/report")
async def report(cid: int, db=Depends(get_db), current=Depends(require_permission("service:view"))):
    return await download_report(db, await owned(db, ServiceCall, cid, current))


async def gateway_client(request: Request, x_api_key: str = Header(default=""), db=Depends(get_db)):
    client = await db.scalar(select(ServiceClient).where(ServiceClient.key_hash == sha256(x_api_key.encode()).hexdigest()))
    if not client or not client.active:
        db.add(ServiceCall(tenant_id=0, status="unauthorized", detail="gateway_auth_failed"))
        await db.commit()
        raise HTTPException(401, "API Key 无效或已撤销")
    user = await db.get(User, client.creator_id)
    tenant = await db.get(Tenant, client.tenant_id)
    if not user or user.status != "active" or user.tenant_id != client.tenant_id or not tenant or tenant.status != "active":
        raise HTTPException(401, "接入方主体不可用")
    from app.services.rbac import get_user_permissions
    if "service:create" not in await get_user_permissions(db, user):
        raise HTTPException(403, "接入方主体已失去服务调用权限")
    from datetime import datetime, timedelta
    from sqlalchemy import func
    recent = await db.scalar(select(func.count()).select_from(ServiceGatewayAudit).where(
        ServiceGatewayAudit.client_id == client.id, ServiceGatewayAudit.status_code != 429,
        ServiceGatewayAudit.created_at >= datetime.utcnow() - timedelta(minutes=1)))
    if recent >= client.requests_per_minute:
        raise HTTPException(429, "API 网关请求频率超限，请稍后重试")
    return client, user


@gateway.get("/services")
async def discover_services(db=Depends(get_db), identity=Depends(gateway_client)):
    client, user = identity
    return await routes(client.workspace_id, db, user)


@gateway.get("/usage")
async def gateway_usage(db=Depends(get_db), identity=Depends(gateway_client)):
    client, _ = identity
    return {"daily_tokens": client.daily_tokens, "monthly_tokens": client.monthly_tokens,
            "requests_per_minute": client.requests_per_minute, **await client_usage(db, client)}


@router.get("/gateway-audit")
async def gateway_audit(workspace_id: int, page: int = Query(1, ge=1), db=Depends(get_db), current=Depends(require_permission("service:view"))):
    await workspace_for(db, workspace_id, current.tenant_id)
    rows = (await db.scalars(select(ServiceGatewayAudit).join(ServiceClient, ServiceClient.id == ServiceGatewayAudit.client_id)
        .where(ServiceClient.workspace_id == workspace_id, ServiceGatewayAudit.tenant_id == current.tenant_id)
        .order_by(ServiceGatewayAudit.id.desc()).offset((page - 1) * 50).limit(50))).all()
    return {"items": [{"id": r.id, "client_id": r.client_id, "method": r.method, "path": r.path,
                       "status_code": r.status_code, "created_at": r.created_at.isoformat()} for r in rows]}


@gateway.post("/evaluations")
async def gateway_evaluate(body: EvaluationBody, request: Request, idempotency_key: str = Header(...),
                           db=Depends(get_db), identity=Depends(gateway_client)):
    client, user = identity
    return await audited_evaluate(body, request, db, user, idempotency_key, client.id)


@gateway.get("/evaluations/{cid}")
async def gateway_status(cid: int, db=Depends(get_db), identity=Depends(gateway_client)):
    client, user = identity
    call = await owned(db, ServiceCall, cid, user)
    if call.client_id != client.id:
        raise HTTPException(404, "评测调用不存在")
    return await call_out(db, call)


@gateway.get("/evaluations/{cid}/report")
async def gateway_report(cid: int, db=Depends(get_db), identity=Depends(gateway_client)):
    client, user = identity
    call = await owned(db, ServiceCall, cid, user)
    if call.client_id != client.id:
        raise HTTPException(404, "评测调用不存在")
    return await download_report(db, call)
