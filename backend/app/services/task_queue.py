"""优先级队列：依赖、并发上限、执行窗口；经 claim/lease 领取。"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import EvalTask
from app.services.task_service import claim_next, enqueue_task as _enqueue

log = logging.getLogger(__name__)

MAX_PARALLEL = 4


async def enqueue_task(db: AsyncSession, task: EvalTask) -> EvalTask:
    return await _enqueue(db, task)


async def dispatch_queue(prefer_id: int | None = None) -> None:
    from app.services.task_runner import run_eval_task

    async with async_session() as db:
        claimed, token = await claim_next(db, prefer_id=prefer_id, max_parallel=MAX_PARALLEL)
        if not claimed:
            await db.commit()
            return
        tid = claimed.id
        owner = claimed.lease_owner
        await db.commit()

    await run_eval_task(tid, fencing_token=token, lease_owner=owner)


async def dispatch_dependents(parent_id: int) -> None:
    from sqlalchemy import select

    ids: list[int] = []
    async with async_session() as db:
        rows = (
            await db.execute(
                select(EvalTask)
                .where(EvalTask.status == "queued", EvalTask.depends_on_id == parent_id)
                .order_by(EvalTask.priority.desc(), EvalTask.id.asc())
            )
        ).scalars().all()
        ids = [t.id for t in rows]
    for tid in ids:
        await dispatch_queue(tid)
