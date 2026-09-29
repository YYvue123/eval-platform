"""运维工单状态机、演练留痕、授权与运营报表。"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ops_governance import DataAuthorization, OpsDrillRecord, OpsTicket
from app.utils.jsonutil import dumps, loads

TICKET_STATUSES = {"open", "in_progress", "resolved", "closed", "disabled"}
CLOSE_STATUSES = {"resolved", "closed"}
POLICY_VERSION = "2026-09-28-wp16"


def ticket_out(t: OpsTicket) -> dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "category": t.category,
        "severity": t.severity,
        "status": t.status,
        "owner_id": t.owner_id,
        "reporter_id": t.reporter_id,
        "tenant_id": t.tenant_id,
        "detail": t.detail,
        "resolution": t.resolution,
        "created_at": t.created_at.isoformat() + "Z" if t.created_at else None,
        "updated_at": t.updated_at.isoformat() + "Z" if t.updated_at else None,
        "closed_at": t.closed_at.isoformat() + "Z" if t.closed_at else None,
    }


def drill_out(d: OpsDrillRecord) -> dict[str, Any]:
    return {
        "id": d.id,
        "drill_type": d.drill_type,
        "operator_id": d.operator_id,
        "result": d.result,
        "checklist": loads(d.checklist_json, []),
        "notes": d.notes,
        "evidence": loads(d.evidence_json, {}),
        "policy_version": d.policy_version,
        "created_at": d.created_at.isoformat() + "Z" if d.created_at else None,
    }


def auth_out(a: DataAuthorization) -> dict[str, Any]:
    return {
        "id": a.id,
        "asset_type": a.asset_type,
        "asset_ref": a.asset_ref,
        "license_spdx": a.license_spdx,
        "grantor": a.grantor,
        "grantee_tenant": a.grantee_tenant,
        "purpose": a.purpose,
        "evidence_uri": a.evidence_uri,
        "status": a.status,
        "disabled": bool(a.disabled),
        "created_by": a.created_by,
        "valid_from": a.valid_from.isoformat() + "Z" if a.valid_from else None,
        "valid_until": a.valid_until.isoformat() + "Z" if a.valid_until else None,
        "created_at": a.created_at.isoformat() + "Z" if a.created_at else None,
    }


async def create_ticket(
    db: AsyncSession,
    *,
    title: str,
    category: str,
    severity: str,
    detail: str,
    reporter_id: int | None,
    tenant_id: int | None,
    owner_id: int | None = None,
) -> OpsTicket:
    t = OpsTicket(
        title=(title or "").strip() or "未命名工单",
        category=category or "general",
        severity=severity or "medium",
        detail=detail or "",
        reporter_id=reporter_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
        status="in_progress" if owner_id else "open",
    )
    db.add(t)
    await db.flush()
    return t


async def update_ticket(
    db: AsyncSession,
    ticket: OpsTicket,
    *,
    status: str | None = None,
    owner_id: int | None = None,
    resolution: str | None = None,
    detail: str | None = None,
    set_owner: bool = False,
) -> OpsTicket:
    if ticket.status == "disabled":
        raise ValueError("已停用工单不可变更（历史保留）")
    if set_owner:
        ticket.owner_id = owner_id
    if detail is not None:
        ticket.detail = detail
    if resolution is not None:
        ticket.resolution = resolution
    if status:
        if status not in TICKET_STATUSES:
            raise ValueError(f"非法状态: {status}")
        if status in CLOSE_STATUSES:
            if not ticket.owner_id and not (set_owner and owner_id):
                raise ValueError("关闭/解决工单必须指定负责人 owner_id")
            if set_owner and owner_id:
                ticket.owner_id = owner_id
            if not (resolution or ticket.resolution or "").strip():
                raise ValueError("关闭/解决工单必须填写 resolution")
            ticket.closed_at = datetime.utcnow()
        if status == "disabled":
            # 停用不删记录
            ticket.closed_at = ticket.closed_at or datetime.utcnow()
        ticket.status = status
    elif set_owner and owner_id and ticket.status == "open":
        ticket.status = "in_progress"
    ticket.updated_at = datetime.utcnow()
    await db.flush()
    return ticket


def _drill_pass_error(evidence: dict, operator_id: int | None, operator_name: str | None) -> str | None:
    rel = str(evidence.get("artifact_path") or "").replace("\\", "/").strip()
    digest = str(evidence.get("sha256") or "").strip().lower()
    if not rel or Path(rel).is_absolute() or ".." in rel.split("/") or ":" in rel:
        return "drill_pass_requires_artifact:正式通过需要 BACKUP_DIR 内相对路径制品"
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        return "drill_pass_requires_artifact:sha256 必须是制品内容的 64 位十六进制摘要"
    root = Path(os.environ.get("BACKUP_DIR") or "backups").resolve()
    path = (root / rel).resolve()
    if path != root and root not in path.parents:
        return "drill_pass_requires_artifact:证据路径越界"
    if not path.is_file():
        return "drill_pass_requires_artifact:制品不存在"
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != digest:
        return "drill_pass_requires_artifact:sha256 与制品不一致"
    signer = str(evidence.get("signed_by") or "").strip()
    if not operator_id or not operator_name or signer != operator_name:
        return "drill_pass_requires_signer:signed_by 必须为当前登录操作者"
    if not str(evidence.get("signed_at") or "").strip():
        return "drill_pass_requires_signer:缺少 signed_at"
    return None


async def record_drill(
    db: AsyncSession,
    *,
    drill_type: str,
    operator_id: int | None,
    result: str,
    checklist: list,
    notes: str,
    evidence: dict,
    policy_version: str = POLICY_VERSION,
    operator_name: str | None = None,
) -> OpsDrillRecord:
    evidence = evidence or {}
    result = (result or "draft").strip().lower()
    if result == "pass":
        reason = _drill_pass_error(evidence, operator_id, operator_name)
        if reason:
            raise ValueError(reason)
    if result not in {"pass", "fail", "draft", "not_run", "blocked"}:
        result = "draft"
    d = OpsDrillRecord(
        drill_type=drill_type or "restore",
        operator_id=operator_id,
        result=result,
        checklist_json=dumps(checklist or []),
        notes=notes or "",
        evidence_json=dumps(evidence),
        policy_version=policy_version or POLICY_VERSION,
    )
    db.add(d)
    await db.flush()
    return d


async def create_authorization(
    db: AsyncSession,
    *,
    asset_type: str,
    asset_ref: str,
    license_spdx: str,
    grantor: str,
    grantee_tenant: str,
    purpose: str,
    evidence_uri: str,
    created_by: int | None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> DataAuthorization:
    if not (license_spdx or "").strip():
        raise ValueError("license_spdx 必填")
    if not (grantor or "").strip():
        raise ValueError("grantor 必填")
    a = DataAuthorization(
        asset_type=asset_type or "dataset",
        asset_ref=asset_ref or "",
        license_spdx=license_spdx.strip(),
        grantor=grantor.strip(),
        grantee_tenant=grantee_tenant or "",
        purpose=purpose or "",
        evidence_uri=evidence_uri or "",
        created_by=created_by,
        valid_from=valid_from,
        valid_until=valid_until,
        status="active",
    )
    db.add(a)
    await db.flush()
    return a


async def disable_authorization(db: AsyncSession, a: DataAuthorization) -> DataAuthorization:
    a.disabled = True
    a.status = "disabled"
    a.updated_at = datetime.utcnow()
    await db.flush()
    return a


async def ops_report(db: AsyncSession) -> dict[str, Any]:
    from app.models import AuditLog, EvalTask
    from app.services.admission import last_admission
    from app.services.degrade import get_degrade
    from app.services.metrics import snapshot

    open_n = await db.scalar(
        select(func.count()).select_from(OpsTicket).where(OpsTicket.status.in_(["open", "in_progress"]))
    ) or 0
    closed_n = await db.scalar(
        select(func.count()).select_from(OpsTicket).where(OpsTicket.status.in_(["resolved", "closed"]))
    ) or 0
    drill_n = await db.scalar(select(func.count()).select_from(OpsDrillRecord)) or 0
    auth_n = await db.scalar(
        select(func.count()).select_from(DataAuthorization).where(DataAuthorization.disabled.is_(False))
    ) or 0
    task_n = await db.scalar(select(func.count()).select_from(EvalTask)) or 0
    audit_n = await db.scalar(select(func.count()).select_from(AuditLog)) or 0
    last_drill = (
        await db.execute(select(OpsDrillRecord).order_by(OpsDrillRecord.id.desc()).limit(1))
    ).scalar_one_or_none()
    return {
        "policy_version": POLICY_VERSION,
        "tickets": {"open": open_n, "closed": closed_n},
        "drills": {"total": drill_n, "latest": drill_out(last_drill) if last_drill else None},
        "authorizations_active": auth_n,
        "tasks_total": task_n,
        "audit_total": audit_n,
        "metrics": snapshot(),
        "degrade": get_degrade(),
        "last_admission": last_admission(),
        "benchmark_ecosystem": {
            "documented": True,
            "path": "docs/operations/benchmark-ecosystem.md",
            "note": "空白章节仅列 TBD，不虚构承诺",
        },
    }
