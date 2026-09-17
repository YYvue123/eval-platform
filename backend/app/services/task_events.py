"""任务事件总线与告警。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlertPolicy, Notification, TaskEvent
from app.utils.jsonutil import dumps


async def emit_event(db: AsyncSession, task_id: int, event_type: str, payload: dict | None = None) -> TaskEvent:
    ev = TaskEvent(task_id=task_id, event_type=event_type, payload_json=dumps(payload or {}))
    db.add(ev)
    await db.flush()
    await maybe_alert(db, task_id, event_type, payload or {})
    return ev


async def maybe_alert(db: AsyncSession, task_id: int, event_type: str, payload: dict) -> None:
    policies = (await db.execute(
        select(AlertPolicy).where(AlertPolicy.event_type == event_type, AlertPolicy.enabled == True)  # noqa: E712
    )).scalars().all()
    for p in policies:
        db.add(Notification(
            user_id=None,
            title=p.title or event_type,
            message=f"任务 {task_id}：{event_type} {payload}",
            type="warning" if "fail" in event_type or "timeout" in event_type else "info",
        ))
    await db.flush()
