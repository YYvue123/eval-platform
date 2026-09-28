"""服务单用量结算：幂等交付，流水只增不删（冲正用 adjust）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EvalServiceRequest, EvalTask, EvalWorkspace, UsageLedger
from app.utils.jsonutil import dumps


def delivery_idem_key(service_id: int) -> str:
    return f"service-delivery:{service_id}"


async def find_delivery_ledger(db: AsyncSession, service_id: int) -> UsageLedger | None:
    key = delivery_idem_key(service_id)
    return await db.scalar(
        select(UsageLedger).where(
            UsageLedger.subject_type == "service",
            UsageLedger.subject_id == str(service_id),
            UsageLedger.entry_type == "settle",
            UsageLedger.note == key,
        ).order_by(UsageLedger.id.desc())
    )


async def settle_service_delivery(
    db: AsyncSession,
    service: EvalServiceRequest,
    *,
    tokens: int = 0,
) -> dict:
    """
    交付结算：同一服务单重复调用不重复扣费。
    要求已有报告（report_path 或绑定任务报告）。
    """
    if not (service.report_path or "").strip() and not service.task_id:
        raise ValueError("report_required_before_delivered")

    # 若绑定任务，补齐报告路径
    if service.task_id:
        task = await db.get(EvalTask, service.task_id)
        if task:
            if not service.report_path and task.report_path:
                service.report_path = task.report_path
            if not service.report_summary and task.report_summary:
                service.report_summary = task.report_summary
            if not tokens:
                tokens = int(getattr(task, "tokens_used", 0) or 0)

    if not (service.report_path or "").strip() and not (service.report_summary or "").strip():
        # 允许 summary 但必须至少有路径或明确任务报告；严格验收：无文件路径拒绝
        if not service.task_id:
            raise ValueError("report_required_before_delivered")
        task = await db.get(EvalTask, service.task_id)
        if not task or not (task.report_path or "").strip():
            raise ValueError("report_required_before_delivered")

    existing = await find_delivery_ledger(db, service.id)
    if existing or service.delivery_settled:
        return {
            "settled": True,
            "idempotent": True,
            "ledger_id": existing.id if existing else None,
            "tokens": 0,
        }

    tokens = max(int(tokens or 0), 0)
    balance = 0
    if service.workspace_id:
        ws = await db.get(EvalWorkspace, service.workspace_id)
        if ws:
            ws.used_tokens = int(ws.used_tokens or 0) + tokens
            ws.used_calls = int(ws.used_calls or 0) + 1
            balance = int(ws.used_tokens)

    ledger = UsageLedger(
        subject_type="service",
        subject_id=str(service.id),
        tenant_id=str(getattr(service, "tenant_id", "") or ""),
        entry_type="settle",
        amount=tokens,
        balance_after=balance,
        note=delivery_idem_key(service.id),
    )
    db.add(ledger)
    service.delivery_settled = True
    await db.flush()
    return {
        "settled": True,
        "idempotent": False,
        "ledger_id": ledger.id,
        "tokens": tokens,
        "meta": dumps({"quote_version": service.quote_version, "quote_amount": service.quote_amount}),
    }


async def reverse_delivery(db: AsyncSession, service_id: int, note: str = "冲正") -> UsageLedger | None:
    """财务冲正：写入负向 adjust，不删除原流水。"""
    original = await find_delivery_ledger(db, service_id)
    if not original:
        return None
    adj = UsageLedger(
        subject_type="service",
        subject_id=str(service_id),
        tenant_id=original.tenant_id,
        entry_type="adjust",
        amount=-int(original.amount or 0),
        balance_after=max(int(original.balance_after or 0) - int(original.amount or 0), 0),
        note=f"reverse:{delivery_idem_key(service_id)}:{note}",
    )
    db.add(adj)
    await db.flush()
    return adj
