"""优先级队列：依赖、并发上限、执行窗口。"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import EvalTask
from app.services.task_events import emit_event

log = logging.getLogger(__name__)

MAX_PARALLEL = 4


def _in_window(task: EvalTask, now: datetime) -> bool:
    if task.window_start and now < task.window_start:
        return False
    if task.window_end and now > task.window_end:
        return False
    return True


async def deps_ready(db: AsyncSession, task: EvalTask) -> bool:
    if not task.depends_on_id:
        return True
    dep = await db.get(EvalTask, task.depends_on_id)
    return bool(dep and dep.status == "success")


async def dispatch_queue(prefer_id: int | None = None) -> None:
    from app.services.task_runner import run_eval_task

    to_start: list[int] = []
    async with async_session() as db:
        running = await db.scalar(select(func.count()).select_from(EvalTask).where(EvalTask.status == "running")) or 0
        slots = max(MAX_PARALLEL - int(running), 0)
        if slots <= 0:
            return
        now = datetime.utcnow()
        q = select(EvalTask).where(EvalTask.status == "queued").order_by(EvalTask.priority.desc(), EvalTask.id.asc())
        queued = (await db.execute(q)).scalars().all()
        if prefer_id:
            queued = [t for t in queued if t.id == prefer_id]
        for task in queued:
            if slots <= 0:
                break
            if not _in_window(task, now):
                await emit_event(db, task.id, "window_wait", {})
                continue
            if not await deps_ready(db, task):
                await emit_event(db, task.id, "dep_wait", {"depends_on_id": task.depends_on_id})
                continue
            to_start.append(task.id)
            slots -= 1
        await db.commit()

    for tid in to_start:
        await run_eval_task(tid)


async def dispatch_dependents(parent_id: int) -> None:
    ids: list[int] = []
    async with async_session() as db:
        rows = (await db.execute(
            select(EvalTask).where(EvalTask.status == "queued", EvalTask.depends_on_id == parent_id).order_by(EvalTask.priority.desc(), EvalTask.id.asc())
        )).scalars().all()
        ids = [t.id for t in rows]
    for tid in ids:
        await dispatch_queue(tid)


async def enqueue_task(db: AsyncSession, task: EvalTask) -> EvalTask:
    task.status = "queued"
    task.progress = 0
    task.error_message = ""
    await emit_event(db, task.id, "queued", {"priority": task.priority})
    await db.flush()
    return task
