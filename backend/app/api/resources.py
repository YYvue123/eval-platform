"""智能工具底座：Manifest 注册、发现、信封调用、事件。"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.database import get_db
from app.models import BaseResource, ResourceCallLog, ResourceEvent, User
from app.services.audit import get_client_ip, log_audit
from app.services.builtin_tools import run_builtin_tool
from app.services.gateway import check_gateway, record_gateway
from app.services.skill_runtime import run_mcp, run_skill
from app.services.protocol import make_envelope, make_response, validate_manifest
from app.services.serializers import now
from app.utils.jsonutil import dumps, iso, loads

router = APIRouter()


class ManifestBody(BaseModel):
    manifest: dict


class InvokeBody(BaseModel):
    resource_id: str
    body: dict = {}
    tenant_id: str = ""
    correlation_id: str | None = None
    priority: str = "normal"


class MatchBody(BaseModel):
    resource_type: str = ""
    judge_type: str = ""
    call_mode: str = ""
    name: str = ""


def resource_out(r: BaseResource):
    return {
        "id": r.id,
        "resource_id": r.resource_id,
        "resource_type": r.resource_type,
        "name": r.name,
        "version": r.version,
        "spec_version": r.spec_version,
        "description": r.description,
        "status": r.status,
        "builtin": r.builtin,
        "health_status": r.health_status,
        "call_count": r.call_count,
        "fail_count": r.fail_count,
        "manifest": loads(r.manifest_json, {}),
        "quality_report": loads(r.quality_report, {}),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


async def _emit(db, event_type: str, resource_id: str, payload: dict | None = None):
    db.add(ResourceEvent(event_type=event_type, resource_id=resource_id, payload_json=dumps(payload or {})))


async def _load_resource(db, rid: str) -> BaseResource | None:
    r = (await db.execute(select(BaseResource).where(BaseResource.resource_id == rid))).scalar_one_or_none()
    if r:
        return r
    try:
        return await db.get(BaseResource, int(rid))
    except ValueError:
        return None


@router.get("")
async def list_resources(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    resource_type: str = Query(""),
    status: str = Query(""),
    search: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("resource:list")),
):
    q = select(BaseResource)
    if resource_type:
        q = q.where(BaseResource.resource_type == resource_type)
    if status:
        q = q.where(BaseResource.status == status)
    if search:
        q = q.where(or_(BaseResource.name.contains(search), BaseResource.resource_id.contains(search)))
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(BaseResource.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [resource_out(r) for r in rows], "total": total or 0}


@router.post("/match")
async def match_resources(
    body: MatchBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("resource:list")),
):
    rows = (await db.execute(select(BaseResource).where(BaseResource.status == "online"))).scalars().all()
    matched = []
    for r in rows:
        mf = loads(r.manifest_json, {})
        spec = mf.get("evaluation_spec") or {}
        caps = mf.get("capabilities") or {}
        if body.resource_type and r.resource_type != body.resource_type:
            continue
        if body.judge_type and spec.get("judge_type") != body.judge_type:
            continue
        if body.call_mode and caps.get("call_mode") != body.call_mode:
            continue
        if body.name and body.name.lower() not in (r.name or "").lower() and body.name.lower() not in r.resource_id:
            continue
        matched.append(resource_out(r))
    return {"items": matched, "total": len(matched)}


@router.get("/registry")
async def resource_registry(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("resource:list")),
):
    """进程内注册中心：在线资源发现；连续失败 5 次健康剔除。"""
    rows = (await db.execute(select(BaseResource))).scalars().all()
    items = []
    for r in rows:
        if not r.builtin and int(r.consecutive_fail or 0) >= 5 and r.status == "online":
            r.status = "unhealthy"
            r.health_status = "abnormal"
            await _emit(db, "resource.unhealthy", r.resource_id, {"consecutive_fail": r.consecutive_fail})
        if r.status in {"online", "pending"}:
            items.append({
                **resource_out(r),
                "instance": "in-process",
                "last_heartbeat": iso(getattr(r, "last_heartbeat", None) or r.updated_at),
            })
    return {"items": items, "total": len(items), "backend": "in-process"}


@router.post("/{rid:path}/heartbeat")
async def resource_heartbeat(
    rid: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("resource:invoke")),
):
    r = await _load_resource(db, rid)
    if not r:
        raise HTTPException(404, "资源不存在")
    from datetime import datetime
    r.last_heartbeat = datetime.utcnow()
    r.health_status = "online"
    if r.status == "unhealthy":
        r.status = "online"
        r.consecutive_fail = 0
    return {"ok": True, "resource_id": r.resource_id, "status": r.status}


@router.get("/events")
async def list_events(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("resource:view")),
):
    rows = (await db.execute(select(ResourceEvent).order_by(ResourceEvent.id.desc()).limit(limit))).scalars().all()
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "resource_id": e.resource_id,
            "payload": loads(e.payload_json, {}),
            "created_at": iso(e.created_at),
        }
        for e in rows
    ]


@router.post("/register")
async def register_resource(
    body: ManifestBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("resource:create")),
):
    errors = validate_manifest(body.manifest)
    if errors:
        raise HTTPException(400, "Manifest 校验失败: " + "；".join(errors))
    rid = body.manifest["resource_id"]
    existing = (await db.execute(select(BaseResource).where(BaseResource.resource_id == rid))).scalar_one_or_none()
    report = {"passed": True, "checks": ["schema", "resource_id", "capabilities"]}
    created = False
    if existing:
        existing.manifest_json = dumps(body.manifest)
        existing.name = body.manifest["name"]
        existing.version = body.manifest["version"]
        existing.description = body.manifest.get("description", "")
        existing.spec_version = str(body.manifest.get("spec_version", "0.6.1"))
        existing.quality_report = dumps(report)
        existing.status = "online"
        existing.health_status = "online"
        existing.updated_at = now()
        r = existing
    else:
        created = True
        r = BaseResource(
            resource_id=rid,
            resource_type=body.manifest["resource_type"],
            name=body.manifest["name"],
            version=body.manifest["version"],
            spec_version=str(body.manifest.get("spec_version", "0.6.1")),
            description=body.manifest.get("description", ""),
            status="online",
            manifest_json=dumps(body.manifest),
            quality_report=dumps(report),
            health_status="online",
            creator_id=current.id,
        )
        db.add(r)
        await db.flush()
    await _emit(db, "resource.registered" if created else "resource.updated", rid, {"version": r.version})
    await log_audit(db, "resource", "register", user_id=current.id, username=current.username, target_id=r.id, ip=get_client_ip(request), detail=rid)
    return resource_out(r)


@router.post("/invoke")
async def invoke_resource(
    body: InvokeBody,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("resource:invoke")),
):
    r = (await db.execute(select(BaseResource).where(BaseResource.resource_id == body.resource_id))).scalar_one_or_none()
    if not r or r.status not in {"online", "pending"}:
        raise HTTPException(404, "资源不可用")
    check_gateway(r.resource_id)
    req = make_envelope(
        "platform",
        body.resource_id,
        body.body,
        tenant_id=body.tenant_id,
        correlation_id=body.correlation_id,
        priority=body.priority,
    )
    manifest = loads(r.manifest_json, {})
    caps = manifest.get("capabilities") or {}
    if caps.get("side_effects") and caps.get("side_effects") not in {"none", False}:
        result = {"mocked": True, "message": "副作用已沙箱 Mock"}
        record_gateway(r.resource_id, True)
        r.call_count += 1
        return make_response(req, "ok", result, usage={"total_tokens": 0})
    try:
        if r.resource_type == "skill":
            result = run_skill(manifest, body.body)
        elif r.resource_type == "mcp":
            result = run_mcp(body.body)
        elif r.resource_id.startswith("builtin/") or r.builtin:
            result = run_builtin_tool(r.resource_id, body.body)
        else:
            result = await invoke_http_tool(manifest, req)
        r.call_count += 1
        r.fail_count = r.fail_count
        r.consecutive_fail = 0
        r.health_status = "online"
        record_gateway(r.resource_id, True)
        db.add(ResourceCallLog(resource_id=r.resource_id, status="success", correlation_id=req["header"]["correlation_id"]))
        usage = result.get("usage") if isinstance(result, dict) else None
        return make_response(req, "ok", result if isinstance(result, dict) else {"result": result}, usage=usage)
    except HTTPException:
        raise
    except Exception as exc:
        r.fail_count += 1
        r.consecutive_fail = int(r.consecutive_fail or 0) + 1
        record_gateway(r.resource_id, False)
        db.add(ResourceCallLog(resource_id=r.resource_id, status="failed", error_message=str(exc)[:2000], correlation_id=req["header"]["correlation_id"]))
        return make_response(req, "error", {}, error={"code": "TOOL_EXEC_FAILED", "message": str(exc)})


@router.post("/{rid:path}/health")
async def resource_health(
    rid: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("resource:view")),
):
    r = await _load_resource(db, rid)
    if not r:
        raise HTTPException(404, "资源不存在")
    if r.builtin or r.resource_id.startswith("builtin/"):
        r.health_status = "online"
        return {"ok": True, "status": "online", "detail": "builtin"}
    result = await health_http_tool(loads(r.manifest_json, {}))
    r.health_status = "online" if result.get("ok") else "abnormal"
    return result


@router.post("/{rid:path}/offline")
async def offline_resource(
    rid: str,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("resource:edit")),
):
    r = await _load_resource(db, rid)
    if not r:
        raise HTTPException(404, "资源不存在")
    if r.builtin:
        raise HTTPException(400, "内置工具不可下线")
    r.status = "offline"
    await _emit(db, "resource.offline", r.resource_id, {})
    return resource_out(r)


@router.get("/{rid:path}")
async def get_resource(
    rid: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("resource:view")),
):
    r = await _load_resource(db, rid)
    if not r:
        raise HTTPException(404, "资源不存在")
    return resource_out(r)
