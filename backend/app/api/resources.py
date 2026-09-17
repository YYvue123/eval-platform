"""智能工具底座：Manifest 注册、发现、信封调用、批量分片。"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.database import get_db
from app.models import BaseResource, Dataset, DatasetItem, ResourceCallLog, User
from app.services.audit import get_client_ip, log_audit
from app.services.builtin_tools import run_builtin_tool
from app.services.protocol import make_envelope, make_response, validate_manifest
from app.services.serializers import now
from app.utils.jsonutil import dumps, loads

router = APIRouter()


class ManifestBody(BaseModel):
    manifest: dict


class InvokeBody(BaseModel):
    resource_id: str
    body: dict = {}


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


@router.get("/batch/{batch_id}/shards/{shard_id}")
async def get_shard(
    batch_id: str,
    shard_id: int,
    snapshot_id: str = Query(""),
    dataset_id: int = Query(...),
    version_id: int | None = None,
    shard_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("resource:invoke")),
):
    ds = await db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "数据集不存在")
    vid = version_id or ds.current_version_id
    rows = (await db.execute(select(DatasetItem).where(DatasetItem.version_id == vid).order_by(DatasetItem.item_no))).scalars().all()
    start = shard_id * shard_size
    part = rows[start:start + shard_size]
    return {
        "batch_id": batch_id,
        "snapshot_id": snapshot_id,
        "shard_id": shard_id,
        "items": [
            {"id": x.id, "item_no": x.item_no, "input": x.input_content, "reference": x.reference_answer}
            for x in part
        ],
        "done": start + shard_size >= len(rows),
    }


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
    if existing:
        existing.manifest_json = dumps(body.manifest)
        existing.name = body.manifest["name"]
        existing.version = body.manifest["version"]
        existing.description = body.manifest.get("description", "")
        existing.spec_version = str(body.manifest.get("spec_version", "0.6.1"))
        existing.quality_report = dumps(report)
        existing.status = "online"
        existing.updated_at = now()
        r = existing
    else:
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
    await log_audit(db, "resource", "register", user_id=current.id, username=current.username, target_id=r.id, ip=get_client_ip(request), detail=rid)
    return resource_out(r)


@router.get("/{rid:path}")
async def get_resource(
    rid: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("resource:view")),
):
    r = (await db.execute(select(BaseResource).where(BaseResource.resource_id == rid))).scalar_one_or_none()
    if not r:
        try:
            r = await db.get(BaseResource, int(rid))
        except ValueError:
            r = None
    if not r:
        raise HTTPException(404, "资源不存在")
    return resource_out(r)


@router.post("/{rid:path}/offline")
async def offline_resource(
    rid: str,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("resource:edit")),
):
    r = (await db.execute(select(BaseResource).where(BaseResource.resource_id == rid))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "资源不存在")
    if r.builtin:
        raise HTTPException(400, "内置工具不可下线")
    r.status = "offline"
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
    req = make_envelope("platform", body.resource_id, body.body)
    try:
        if r.resource_id.startswith("builtin/"):
            result = run_builtin_tool(r.resource_id, body.body)
        else:
            raise HTTPException(400, "当前仅支持内置工具本地调用；外部资源请通过评测任务调度")
        r.call_count += 1
        r.health_status = "online"
        db.add(ResourceCallLog(resource_id=r.resource_id, status="success"))
        return make_response(req, "ok", result)
    except HTTPException:
        raise
    except Exception as exc:
        r.fail_count += 1
        db.add(ResourceCallLog(resource_id=r.resource_id, status="failed", error_message=str(exc)[:2000]))
        return make_response(req, "error", {"error": {"code": "TOOL_EXEC_FAILED", "message": str(exc)}})
