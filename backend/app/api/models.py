"""被测模型管理。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.database import get_db
from app.models import EvalModel, ModelCallLog, User
from app.services.audit import get_client_ip, log_audit
from app.services.model_client import health_check, invoke_model
from app.services.serializers import model_out

router = APIRouter()


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
    status: str = "draft"


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
    status: str | None = None


class InvokeBody(BaseModel):
    prompt: str


@router.get("")
async def list_models(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    search: str = Query(""),
    status: str = Query(""),
    model_source: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("model:list")),
):
    q = select(EvalModel)
    if search:
        q = q.where(or_(EvalModel.name.contains(search), EvalModel.description.contains(search)))
    if status:
        q = q.where(EvalModel.status == status)
    if model_source:
        q = q.where(EvalModel.model_source == model_source)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(EvalModel.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [model_out(m) for m in rows], "total": total or 0}


@router.post("")
async def create_model(
    body: ModelCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("model:create")),
):
    m = EvalModel(**body.model_dump(), creator_id=current.id)
    db.add(m)
    await db.flush()
    await log_audit(db, "model", "create", user_id=current.id, username=current.username, target_id=m.id, ip=get_client_ip(request))
    return model_out(m)


@router.get("/{model_id}")
async def get_model(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("model:view")),
):
    m = await db.get(EvalModel, model_id)
    if not m:
        raise HTTPException(404, "模型不存在")
    logs = (await db.execute(select(ModelCallLog).where(ModelCallLog.model_id == model_id).order_by(ModelCallLog.id.desc()).limit(50))).scalars().all()
    return {
        **model_out(m),
        "logs": [
            {
                "id": lg.id,
                "call_status": lg.call_status,
                "latency_ms": lg.latency_ms,
                "token_usage": lg.token_usage,
                "error_message": lg.error_message,
                "created_at": lg.created_at.isoformat() if lg.created_at else None,
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
    if not m:
        raise HTTPException(404, "模型不存在")
    data = body.model_dump(exclude_unset=True)
    if data.get("api_key") == "":
        data.pop("api_key")
    for k, v in data.items():
        setattr(m, k, v)
    await log_audit(db, "model", "update", user_id=current.id, username=current.username, target_id=m.id, ip=get_client_ip(request))
    return model_out(m)


@router.delete("/{model_id}")
async def delete_model(
    model_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("model:delete")),
):
    m = await db.get(EvalModel, model_id)
    if not m:
        raise HTTPException(404, "模型不存在")
    await db.delete(m)
    await log_audit(db, "model", "delete", user_id=current.id, username=current.username, target_id=model_id, ip=get_client_ip(request))
    return {"ok": True}


@router.post("/{model_id}/health")
async def check_model_health(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("model:view")),
):
    m = await db.get(EvalModel, model_id)
    if not m:
        raise HTTPException(404, "模型不存在")
    result = await health_check(m)
    m.health_status = result["status"]
    m.last_health_at = datetime.utcnow()
    m.last_error = "" if result["ok"] else result.get("detail", "")
    if result["ok"] and m.status == "draft":
        m.status = "online"
    return {**result, "health_status": m.health_status}


@router.post("/{model_id}/invoke")
async def invoke(
    model_id: int,
    body: InvokeBody,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("model:invoke")),
):
    m = await db.get(EvalModel, model_id)
    if not m:
        raise HTTPException(404, "模型不存在")
    try:
        result = await invoke_model(m, body.prompt)
        db.add(ModelCallLog(model_id=m.id, user_id=current.id, call_status="success", latency_ms=result["latency_ms"], token_usage=result["tokens"]))
        return result
    except Exception as exc:
        db.add(ModelCallLog(model_id=m.id, user_id=current.id, call_status="failed", error_message=str(exc)[:2000]))
        raise HTTPException(400, f"调用失败: {exc}") from exc
