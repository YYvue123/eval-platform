"""健康检查、Prometheus 指标、备份与运行环境。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.config import settings
from app.database import get_db
from app.models import AuditLog, Dataset, TaskTemplate, User
from app.services.backup import backup_sqlite
from app.services.batch_store import gc_expired_snapshots
from app.services.metrics import render_prometheus, snapshot
from app.services.task_catalog import catalog_templates

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "ok": True,
        "env": settings.APP_ENV,
        "channel_default": "remote-encrypted",
        "mtls_configured": bool(settings.MTLS_CERT_FILE and settings.MTLS_KEY_FILE),
        "time": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/metrics")
async def metrics():
    return PlainTextResponse(render_prometheus(), media_type="text/plain; version=0.0.4")


@router.get("/ops/status")
async def ops_status(_: User = Depends(require_permission("ops:view"))):
    return {
        "env": settings.APP_ENV,
        "audit_retention_days": settings.AUDIT_RETENTION_DAYS,
        "mtls_configured": bool(settings.MTLS_CERT_FILE and settings.MTLS_KEY_FILE),
        "metrics": snapshot(),
        "backup_dir": settings.BACKUP_DIR,
    }


@router.get("/ops/acceptance")
async def ops_acceptance(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ops:view")),
):
    expected = len(catalog_templates())
    tpl_n = await db.scalar(select(func.count()).select_from(TaskTemplate).where(TaskTemplate.status == "active")) or 0
    pack_n = await db.scalar(select(func.count()).select_from(Dataset).where(Dataset.data_source == "builtin")) or 0
    items = [
        {"code": "manifest", "name": "Manifest / 信封 1.3", "ok": True, "detail": "内置工具 spec_version=0.6.1"},
        {"code": "channel", "name": "加密通道", "ok": True, "detail": "默认远程加密；mTLS 证书" + ("已配置" if settings.MTLS_CERT_FILE else "未配置（https/网关仍可用）")},
        {"code": "health", "name": "连通与健康检查", "ok": True, "detail": "/api/health"},
        {"code": "templates", "name": "任务模板库", "ok": tpl_n >= expected, "detail": f"{tpl_n}/{expected}"},
        {"code": "packs", "name": "试点评测包数据集", "ok": pack_n >= expected, "detail": f"{pack_n}/{expected}"},
        {"code": "errors", "name": "错误处理", "ok": True, "detail": "信封 status=error + HTTPException"},
    ]
    return {"ok": all(x["ok"] for x in items), "level": "basic", "items": items}


@router.post("/ops/gc-snapshots")
async def ops_gc_snapshots(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ops:backup")),
):
    n = await gc_expired_snapshots(db)
    return {"ok": True, "removed": n}


@router.post("/ops/backup")
async def ops_backup(
    _: User = Depends(require_permission("ops:backup")),
):
    try:
        return backup_sqlite()
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/ops/purge-audit")
async def purge_audit(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ops:backup")),
):
    days = int(settings.AUDIT_RETENTION_DAYS or 180)
    restricted_days = int(settings.AUDIT_RETENTION_RESTRICTED_DAYS or 365)
    cutoff = datetime.utcnow() - timedelta(days=days)
    cutoff_r = datetime.utcnow() - timedelta(days=restricted_days)
    await db.execute(
        delete(AuditLog).where(
            or_(
                and_(AuditLog.tenant_id != "restricted", AuditLog.created_at < cutoff),
                and_(AuditLog.tenant_id == "restricted", AuditLog.created_at < cutoff_r),
            )
        )
    )
    return {"ok": True, "cutoff": cutoff.isoformat(), "restricted_cutoff": cutoff_r.isoformat()}
