"""健康检查、Prometheus 指标、备份、准入与运行环境。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.config import settings
from app.database import get_db
from app.models import AuditLog, User
from app.models.ops_governance import DataAuthorization, OpsDrillRecord, OpsTicket
from app.services.admission import last_admission, run_admission
from app.services.backup import backup_sqlite, restore_drill
from app.services.batch_store import gc_expired_snapshots
from app.services.degrade import clear_degrade, get_degrade, is_ready, set_degrade
from app.services import ops_governance as og
from app.services.metrics import render_prometheus, snapshot

router = APIRouter()


@router.get("/live")
async def live():
    """进程存活探针（不查 DB）。"""
    return {"ok": True, "status": "alive", "time": datetime.utcnow().isoformat() + "Z"}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    """就绪探针：降级标志 + DB 连通。"""
    ok, reason = is_ready()
    db_ok = False
    db_ms = None
    if ok:
        try:
            import time

            t0 = time.perf_counter()
            await db.execute(text("SELECT 1"))
            db_ms = round((time.perf_counter() - t0) * 1000, 2)
            db_ok = True
        except Exception as exc:  # noqa: BLE001
            ok = False
            reason = f"db_error:{exc}"
    else:
        db_ok = False
    body = {
        "ok": ok and db_ok,
        "status": "ready" if (ok and db_ok) else "not_ready",
        "reason": reason if not (ok and db_ok) else "ok",
        "db_ok": db_ok,
        "db_latency_ms": db_ms,
        "degrade": get_degrade(),
        "env": settings.APP_ENV,
        "time": datetime.utcnow().isoformat() + "Z",
    }
    if not body["ok"]:
        return JSONResponse(status_code=503, content=body)
    return body


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """兼容旧探针：等价于精简 readiness（含 DB）。"""
    ok, reason = is_ready()
    db_ok = False
    if ok:
        try:
            await db.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            ok = False
            reason = "db_unavailable"
    body = {
        "ok": ok and db_ok,
        "env": settings.APP_ENV,
        "channel_default": "remote-encrypted",
        "mtls_configured": bool(settings.MTLS_CERT_FILE and settings.MTLS_KEY_FILE),
        "time": datetime.utcnow().isoformat() + "Z",
        "live": True,
        "ready": ok and db_ok,
        "reason": reason if not (ok and db_ok) else "ok",
    }
    if not body["ok"]:
        return JSONResponse(status_code=503, content=body)
    return body


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
        "degrade": get_degrade(),
        "last_admission": last_admission(),
    }


@router.get("/ops/acceptance")
async def ops_acceptance(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ops:view")),
):
    """兼容旧验收页：委托 AdmissionRunner（不再写死 True）。"""
    report = await run_admission(db, level="basic")
    return {
        "ok": report["ok"],
        "level": report["level"],
        "items": report["items"],
        "admission_id": report["id"],
        "artifact_hash": report["artifact_hash"],
        "elapsed_ms": report["elapsed_ms"],
    }


class AdmissionBody(BaseModel):
    level: str = Field(default="basic", pattern="^(basic|full)$")


@router.post("/ops/admission/run")
async def ops_admission_run(
    body: AdmissionBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ops:admit")),
):
    return await run_admission(db, level=body.level)


@router.get("/ops/admission/latest")
async def ops_admission_latest(_: User = Depends(require_permission("ops:view"))):
    last = last_admission()
    if not last:
        raise HTTPException(404, "尚无准入运行记录")
    return last


class FaultBody(BaseModel):
    db_unavailable: bool | None = None
    cert_expired: bool | None = None
    reason: str = ""
    clear: bool = False


@router.post("/ops/fault")
async def ops_fault(
    body: FaultBody,
    _: User = Depends(require_permission("ops:backup")),
):
    """可控故障注入（仅进程内标志，用于演练 AC44）。"""
    if body.clear:
        return {"ok": True, "degrade": clear_degrade()}
    return {
        "ok": True,
        "degrade": set_degrade(
            db_unavailable=body.db_unavailable,
            cert_expired=body.cert_expired,
            reason=body.reason,
        ),
    }


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


@router.post("/ops/restore-drill")
async def ops_restore_drill(
    backup_path: str | None = Query(default=None),
    _: User = Depends(require_permission("ops:backup")),
):
    try:
        return restore_drill(backup_path=backup_path)
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


# --- WP16 工单 / 演练 / 授权 / 报表 ---


class TicketCreate(BaseModel):
    title: str
    category: str = "general"
    severity: str = "medium"
    detail: str = ""
    owner_id: int | None = None


class TicketPatch(BaseModel):
    status: str | None = None
    owner_id: int | None = None
    resolution: str | None = None
    detail: str | None = None


@router.get("/ops/tickets")
async def list_tickets(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ops:view")),
):
    q = select(OpsTicket).order_by(OpsTicket.id.desc()).limit(200)
    if status:
        q = q.where(OpsTicket.status == status)
    rows = (await db.execute(q)).scalars().all()
    return {"items": [og.ticket_out(t) for t in rows], "total": len(rows)}


@router.post("/ops/tickets")
async def create_ticket(
    body: TicketCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("ops:ticket")),
):
    t = await og.create_ticket(
        db,
        title=body.title,
        category=body.category,
        severity=body.severity,
        detail=body.detail,
        reporter_id=user.id,
        tenant_id=getattr(user, "tenant_id", None),
        owner_id=body.owner_id,
    )
    return og.ticket_out(t)


@router.patch("/ops/tickets/{ticket_id}")
async def patch_ticket(
    ticket_id: int,
    body: TicketPatch,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ops:ticket")),
):
    t = await db.get(OpsTicket, ticket_id)
    if not t:
        raise HTTPException(404, "工单不存在")
    try:
        t = await og.update_ticket(
            db,
            t,
            status=body.status,
            owner_id=body.owner_id,
            resolution=body.resolution,
            detail=body.detail,
            set_owner=body.owner_id is not None,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return og.ticket_out(t)


class DrillBody(BaseModel):
    drill_type: str = "restore"
    result: str = "draft"
    checklist: list = Field(default_factory=list)
    notes: str = ""
    evidence: dict = Field(default_factory=dict)


@router.get("/ops/drills")
async def list_drills(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ops:view")),
):
    rows = (await db.execute(select(OpsDrillRecord).order_by(OpsDrillRecord.id.desc()).limit(100))).scalars().all()
    return {"items": [og.drill_out(d) for d in rows], "total": len(rows)}


@router.post("/ops/drills")
async def create_drill(
    body: DrillBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("ops:ticket")),
):
    try:
        d = await og.record_drill(
            db,
            drill_type=body.drill_type,
            operator_id=user.id,
            operator_name=user.username,
            result=body.result,
            checklist=body.checklist,
            notes=body.notes,
            evidence=body.evidence,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return og.drill_out(d)


class AuthCreate(BaseModel):
    asset_type: str = "dataset"
    asset_ref: str
    license_spdx: str
    grantor: str
    grantee_tenant: str = ""
    purpose: str = ""
    evidence_uri: str = ""


@router.get("/ops/authorizations")
async def list_authorizations(
    include_disabled: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ops:view")),
):
    q = select(DataAuthorization).order_by(DataAuthorization.id.desc()).limit(200)
    if not include_disabled:
        q = q.where(DataAuthorization.disabled.is_(False))
    rows = (await db.execute(q)).scalars().all()
    return {"items": [og.auth_out(a) for a in rows], "total": len(rows)}


@router.post("/ops/authorizations")
async def create_authorization(
    body: AuthCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("ops:ticket")),
):
    try:
        a = await og.create_authorization(
            db,
            asset_type=body.asset_type,
            asset_ref=body.asset_ref,
            license_spdx=body.license_spdx,
            grantor=body.grantor,
            grantee_tenant=body.grantee_tenant,
            purpose=body.purpose,
            evidence_uri=body.evidence_uri,
            created_by=user.id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return og.auth_out(a)


@router.post("/ops/authorizations/{auth_id}/disable")
async def disable_authorization(
    auth_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ops:ticket")),
):
    a = await db.get(DataAuthorization, auth_id)
    if not a:
        raise HTTPException(404, "授权记录不存在")
    a = await og.disable_authorization(db, a)
    return og.auth_out(a)


@router.get("/ops/report")
async def ops_report_api(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ops:view")),
):
    return await og.ops_report(db)


@router.get("/ops/policy")
async def ops_policy(_: User = Depends(require_permission("ops:view"))):
    """制度索引（版本归档指针，正文在仓库 docs/operations）。"""
    return {
        "version": og.POLICY_VERSION,
        "docs": [
            {"id": "roles-oncall", "path": "docs/operations/roles-oncall.md", "title": "岗位与值班"},
            {"id": "change-incident", "path": "docs/operations/change-incident.md", "title": "变更/故障/漏洞"},
            {"id": "faq-training", "path": "docs/operations/faq-training.md", "title": "FAQ与培训"},
            {"id": "runbook", "path": "docs/operations/WP15-runbook.md", "title": "发布回滚恢复"},
            {"id": "benchmark-ecosystem", "path": "docs/operations/benchmark-ecosystem.md", "title": "基准生态"},
            {"id": "contributing", "path": "CONTRIBUTING.md", "title": "贡献指南"},
            {"id": "licenses", "path": "docs/licenses/THIRD_PARTY.md", "title": "第三方许可"},
        ],
    }
