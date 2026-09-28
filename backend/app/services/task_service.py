"""任务服务：入队、claim/lease/fencing、取消、重试、依赖环检测。"""
from __future__ import annotations

import os
import socket
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EvalResult, EvalTask
from app.services.task_events import emit_event

LEASE_SECONDS = 90


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


async def detect_dependency_cycle(db: AsyncSession, task_id: int | None, depends_on_id: int | None) -> bool:
    """从 depends_on 向上走，若回到 task_id 则成环。"""
    if not depends_on_id:
        return False
    seen: set[int] = set()
    cur = depends_on_id
    while cur:
        if task_id is not None and cur == task_id:
            return True
        if cur in seen:
            return True
        seen.add(cur)
        row = await db.get(EvalTask, cur)
        if not row:
            break
        cur = row.depends_on_id
    return False


async def enqueue_task(db: AsyncSession, task: EvalTask) -> EvalTask:
    if await detect_dependency_cycle(db, task.id, task.depends_on_id):
        raise HTTPException(400, "任务依赖存在环，已拒绝入队")
    task.status = "queued"
    task.progress = task.progress or 0
    task.error_message = ""
    task.cancel_requested = False
    task.lease_owner = ""
    task.lease_until = None
    # 保留 fencing_token 直到 claim 刷新；enqueue 时清零
    task.fencing_token = 0
    task.finished_at = None
    await emit_event(db, task.id, "queued", {"priority": task.priority, "attempt": getattr(task, "attempt", 0) or 0})
    await db.flush()
    return task


async def request_cancel(db: AsyncSession, task: EvalTask) -> EvalTask:
    if task.status in {"success", "failed", "cancelled", "partial_failed"}:
        raise HTTPException(400, "任务已结束")
    task.cancel_requested = True
    if task.status in {"queued", "draft", "pending_review"}:
        task.status = "cancelled"
        task.finished_at = datetime.utcnow()
        task.lease_owner = ""
        task.lease_until = None
        await emit_event(db, task.id, "cancelled", {"phase": "before_run"})
    else:
        await emit_event(db, task.id, "cancel_requested", {})
    await db.flush()
    return task


async def retry_task(db: AsyncSession, task: EvalTask, *, clear_results: bool = True) -> EvalTask:
    if task.status == "running":
        raise HTTPException(400, "任务正在执行，请先取消再重试")
    task.attempt = int(getattr(task, "attempt", 0) or 0) + 1
    if clear_results:
        rows = (await db.execute(select(EvalResult).where(EvalResult.task_id == task.id))).scalars().all()
        for r in rows:
            await db.delete(r)
        task.progress = 0
        task.success_count = 0
        task.fail_count = 0
        task.skip_count = 0
        task.avg_score = 0
        task.pass_rate = 0
        task.tokens_used = 0
        task.report_summary = ""
        task.report_path = ""
    task.error_message = ""
    task.finished_at = None
    await enqueue_task(db, task)
    await emit_event(db, task.id, "retry", {"attempt": task.attempt})
    return task


async def recover_expired_leases(db: AsyncSession) -> int:
    now = datetime.utcnow()
    result = await db.execute(
        update(EvalTask)
        .where(
            EvalTask.status == "running",
            EvalTask.lease_until.is_not(None),
            EvalTask.lease_until < now,
        )
        .values(
            status="queued",
            lease_owner="",
            lease_until=None,
            # fencing 保留，下一次 claim 会换新 token；旧 runner 回写会被拒
        )
    )
    await db.flush()
    return int(result.rowcount or 0)


async def claim_task(
    db: AsyncSession,
    task_id: int,
    *,
    owner: str | None = None,
    lease_seconds: int = LEASE_SECONDS,
) -> tuple[EvalTask | None, int]:
    """短事务条件 claim。成功返回 (task, fencing_token)；失败 (None, 0)。"""
    owner = owner or worker_id()
    token = int(uuid.uuid4().int % 2_000_000_000) + 1
    now = datetime.utcnow()
    lease_until = now + timedelta(seconds=lease_seconds)
    result = await db.execute(
        update(EvalTask)
        .where(
            EvalTask.id == task_id,
            EvalTask.cancel_requested.is_(False),
            or_(
                EvalTask.status == "queued",
                and_(
                    EvalTask.status == "running",
                    or_(EvalTask.lease_until.is_(None), EvalTask.lease_until < now),
                ),
            ),
        )
        .values(
            status="running",
            lease_owner=owner,
            lease_until=lease_until,
            fencing_token=token,
            started_at=now,
        )
    )
    if not result.rowcount:
        return None, 0
    await db.flush()
    task = await db.get(EvalTask, task_id)
    if task:
        await emit_event(db, task.id, "claimed", {"owner": owner, "fencing_token": token})
    return task, token


async def claim_next(
    db: AsyncSession,
    *,
    prefer_id: int | None = None,
    owner: str | None = None,
    max_parallel: int = 4,
) -> tuple[EvalTask | None, int]:
    await recover_expired_leases(db)
    from sqlalchemy import func
    n_running = await db.scalar(select(func.count()).select_from(EvalTask).where(EvalTask.status == "running")) or 0
    if int(n_running) >= max_parallel:
        return None, 0
    now = datetime.utcnow()
    q = select(EvalTask).where(EvalTask.status == "queued", EvalTask.cancel_requested.is_(False)).order_by(
        EvalTask.priority.desc(), EvalTask.id.asc()
    )
    candidates = (await db.execute(q)).scalars().all()
    if prefer_id:
        preferred = [t for t in candidates if t.id == prefer_id]
        others = [t for t in candidates if t.id != prefer_id]
        candidates = preferred + others
    for task in candidates:
        if task.window_start and now < task.window_start:
            await emit_event(db, task.id, "window_wait", {})
            continue
        if task.window_end and now > task.window_end:
            await emit_event(db, task.id, "window_wait", {"reason": "expired"})
            continue
        if task.depends_on_id:
            dep = await db.get(EvalTask, task.depends_on_id)
            if not dep or dep.status != "success":
                if dep and dep.status in {"failed", "cancelled", "partial_failed"}:
                    task.status = "failed"
                    task.error_message = f"上游依赖任务 {task.depends_on_id} 未成功（{dep.status}）"
                    task.finished_at = now
                    await emit_event(db, task.id, "dep_failed", {"depends_on_id": task.depends_on_id, "dep_status": dep.status})
                    await db.flush()
                else:
                    await emit_event(db, task.id, "dep_wait", {"depends_on_id": task.depends_on_id})
                continue
        claimed, token = await claim_task(db, task.id, owner=owner)
        if claimed:
            return claimed, token
    return None, 0


async def heartbeat_lease(db: AsyncSession, task_id: int, fencing_token: int, lease_seconds: int = LEASE_SECONDS) -> bool:
    now = datetime.utcnow()
    result = await db.execute(
        update(EvalTask)
        .where(
            EvalTask.id == task_id,
            EvalTask.status == "running",
            EvalTask.fencing_token == fencing_token,
            EvalTask.cancel_requested.is_(False),
        )
        .values(lease_until=now + timedelta(seconds=lease_seconds))
    )
    return bool(result.rowcount)


async def fencing_still_valid(db: AsyncSession, task_id: int, fencing_token: int) -> tuple[bool, bool]:
    """返回 (token_ok, cancel_requested)。"""
    row = await db.execute(
        select(EvalTask.fencing_token, EvalTask.cancel_requested, EvalTask.status).where(EvalTask.id == task_id)
    )
    data = row.first()
    if not data:
        return False, True
    token, cancel_req, status = data
    if status == "cancelled" or cancel_req:
        return token == fencing_token, True
    return int(token or 0) == int(fencing_token), False
