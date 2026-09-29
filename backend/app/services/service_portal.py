"""Tenant-bound service routing and usage accounting, backed by real TaskService tasks."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import select

from app.models import EvalTask, EvalWorkspace, ModelCallLog, ServiceCall, ServiceClient

TERMINAL = {"success", "failed", "cancelled", "partial_failed"}


async def workspace_for(db, workspace_id, tenant_id):
    row = await db.scalar(select(EvalWorkspace).where(
        EvalWorkspace.id == workspace_id, EvalWorkspace.tenant_id == tenant_id))
    if not row:
        raise HTTPException(404, "企业工作空间不存在或无权访问")
    return row


def period_starts(now=None):
    # Billing days/months use Asia/Shanghai; database timestamps are UTC.
    now = now or datetime.now(timezone(timedelta(hours=8), "Asia/Shanghai"))
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    utc = timezone.utc
    return day.astimezone(utc).replace(tzinfo=None), month.astimezone(utc).replace(tzinfo=None)


async def call_out(db, call):
    task = await db.get(EvalTask, call.task_id) if call.task_id else None
    used = max(0, int(task.tokens_used or 0)) if task else 0
    cancelled_pause = bool(task and task.status == "paused_budget" and task.cancel_requested)
    terminal = bool(task and (task.status in TERMINAL or cancelled_pause))
    missing_usage = False
    if task:
        missing_usage = bool(await db.scalar(select(ModelCallLog.id).where(
            ModelCallLog.task_id == task.id, ModelCallLog.call_status == "success", ModelCallLog.token_usage <= 0).limit(1)))
        missing_usage = missing_usage or bool(task.success_count and not used)
    reserved = max(call.reserved_tokens, used) if call.status == "accepted" and (not terminal or missing_usage) else used
    return {
        "id": call.id, "client_id": call.client_id, "service_id": call.service_id,
        "task_id": call.task_id, "release_id": call.release_id,
        "status": "cancelled" if cancelled_pause else task.status if task else call.status,
        "progress": task.progress if task else 0,
        "tokens": used, "reserved_tokens": reserved,
        "amount_fen": (used * call.price_fen_per_1k + 999) // 1000,
        "billing_status": "unmeasured" if missing_usage else "settled" if terminal else "pending" if task else "not_charged",
        "report_ready": bool(terminal and task.report_path and not task.trial_run and not task.simulation),
        "detail": call.detail, "created_at": call.created_at.isoformat(),
    }


async def client_usage(db, client: ServiceClient):
    day, month = period_starts()
    rows = (await db.scalars(select(ServiceCall).where(ServiceCall.client_id == client.id))).all()
    daily = monthly = tokens = amount = 0
    for row in rows:
        data = await call_out(db, row)
        pending = data["billing_status"] in {"pending", "unmeasured"}
        if row.created_at >= month or pending:
            monthly += data["reserved_tokens"]
        if row.created_at >= day or pending:
            daily += data["reserved_tokens"]
        if row.created_at >= month:
            tokens += data["tokens"]
            amount += data["amount_fen"]
    return {"daily_used": daily, "monthly_used": monthly, "measured_tokens": tokens,
            "amount_fen": amount, "timezone": "Asia/Shanghai"}


async def check_admission(db, client, budget):
    usage = await client_usage(db, client)
    if usage["daily_used"] + budget > client.daily_tokens:
        raise HTTPException(429, "接入方每日 Token 额度不足")
    if usage["monthly_used"] + budget > client.monthly_tokens:
        raise HTTPException(429, "接入方每月 Token 额度不足")
    from sqlalchemy import func
    count = await db.scalar(select(func.count()).select_from(ServiceCall).where(
        ServiceCall.client_id == client.id, ServiceCall.status == "accepted",
        ServiceCall.created_at >= datetime.utcnow() - timedelta(minutes=1)))
    if count >= client.requests_per_minute:
        raise HTTPException(429, "接入方请求频率超限，请稍后重试")


def choose_release(route, key):
    bucket = int(sha256(key.encode()).hexdigest()[:8], 16) % 100
    return route.candidate_id if route.candidate_id and bucket < route.gray_percent else route.stable_id
