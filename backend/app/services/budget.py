"""预算预占与结算。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UsageLedger, UsageReservation
from app.utils.jsonutil import dumps


async def open_reservation(
    db: AsyncSession,
    *,
    subject_type: str,
    subject_id: str,
    amount: int,
    tenant_id: str = "",
) -> UsageReservation:
    amount = max(int(amount or 0), 0)
    row = UsageReservation(
        subject_type=subject_type,
        subject_id=str(subject_id),
        tenant_id=str(tenant_id or ""),
        reserved=amount,
        settled=0,
        status="open" if amount else "settled",
    )
    db.add(row)
    await db.flush()
    if amount:
        db.add(UsageLedger(
            subject_type=subject_type,
            subject_id=str(subject_id),
            tenant_id=str(tenant_id or ""),
            entry_type="reserve",
            amount=amount,
            balance_after=amount,
            note="预占",
        ))
    return row


async def get_open_reservation(db: AsyncSession, subject_type: str, subject_id: str) -> UsageReservation | None:
    return await db.scalar(
        select(UsageReservation).where(
            UsageReservation.subject_type == subject_type,
            UsageReservation.subject_id == str(subject_id),
            UsageReservation.status.in_(["open", "paused"]),
        ).order_by(UsageReservation.id.desc())
    )


async def settle_tokens(
    db: AsyncSession,
    *,
    subject_type: str,
    subject_id: str,
    amount: int,
    budget: int,
    already_used: int,
    tenant_id: str = "",
) -> tuple[bool, str]:
    """尝试结算 amount。返回 (ok, error_code)。超额则失败且不写入。"""
    amount = max(int(amount or 0), 0)
    if amount <= 0:
        return True, ""
    budget = int(budget or 0)
    if budget and already_used + amount > budget:
        res = await get_open_reservation(db, subject_type, subject_id)
        if res:
            res.status = "paused"
        return False, "BUDGET_EXHAUSTED"
    res = await get_open_reservation(db, subject_type, subject_id)
    if res:
        res.settled = int(res.settled or 0) + amount
        remaining = max(int(res.reserved or 0) - int(res.settled or 0), 0)
        if remaining <= 0 and budget and already_used + amount >= budget:
            res.status = "settled"
    db.add(UsageLedger(
        subject_type=subject_type,
        subject_id=str(subject_id),
        tenant_id=str(tenant_id or ""),
        entry_type="settle",
        amount=amount,
        balance_after=already_used + amount,
        note="结算",
    ))
    return True, ""


async def release_reservation(db: AsyncSession, subject_type: str, subject_id: str, note: str = "释放") -> None:
    res = await get_open_reservation(db, subject_type, subject_id)
    if not res:
        return
    left = max(int(res.reserved or 0) - int(res.settled or 0), 0)
    res.status = "released"
    if left:
        db.add(UsageLedger(
            subject_type=subject_type,
            subject_id=str(subject_id),
            tenant_id=res.tenant_id or "",
            entry_type="release",
            amount=-left,
            balance_after=int(res.settled or 0),
            note=note,
        ))
