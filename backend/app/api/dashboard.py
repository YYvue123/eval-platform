from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Dataset, EvalModel, EvalTask, User
from app.api.deps import require_permission

router = APIRouter()


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("dashboard:view")),
):
    user_count = await db.scalar(select(func.count()).select_from(User)) or 0
    dataset_count = await db.scalar(select(func.count()).select_from(Dataset)) or 0
    model_count = await db.scalar(select(func.count()).select_from(EvalModel)) or 0
    task_count = await db.scalar(select(func.count()).select_from(EvalTask)) or 0
    running = await db.scalar(select(func.count()).select_from(EvalTask).where(EvalTask.status.in_(["queued", "running"]))) or 0
    return {
        "user_count": user_count,
        "dataset_count": dataset_count,
        "model_count": model_count,
        "task_count": task_count,
        "running_task_count": running,
        "message": "",
    }


@router.get("/workbench")
async def get_workbench(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("dashboard:view")),
):
    from app.models import AgentSession

    recent = (await db.execute(select(EvalTask).order_by(EvalTask.id.desc()).limit(8))).scalars().all()
    running_rows = (
        await db.execute(
            select(EvalTask).where(EvalTask.status.in_(["queued", "running"])).order_by(EvalTask.id.desc()).limit(10)
        )
    ).scalars().all()
    failed_rows = (
        await db.execute(select(EvalTask).where(EvalTask.status.in_(["failed", "partial_failed"])).order_by(EvalTask.id.desc()).limit(10))
    ).scalars().all()
    pending_review = (
        await db.execute(
            select(EvalTask).where(EvalTask.status == "pending_review").order_by(EvalTask.id.desc()).limit(10)
        )
    ).scalars().all()
    # 待确认编排会话（非审批单，会话态 waiting_confirm）
    waiting_sessions = (
        await db.execute(
            select(AgentSession).where(AgentSession.status == "waiting_confirm").order_by(AgentSession.id.desc()).limit(10)
        )
    ).scalars().all()
    todos = []
    for t in pending_review:
        todos.append({"kind": "task_review", "id": t.id, "title": t.name, "href": f"/tasks/{t.id}"})
    for s in waiting_sessions:
        todos.append({"kind": "agent_confirm", "id": s.id, "title": s.title or f"会话 #{s.id}", "href": f"/agents?session={s.id}"})
    for t in failed_rows[:5]:
        todos.append({"kind": "task_failed", "id": t.id, "title": t.name, "href": f"/tasks/{t.id}"})
    status_rows = (await db.execute(select(EvalTask.status, func.count()).group_by(EvalTask.status))).all()
    # Group in Shanghai calendar days, including empty days; never infer scoring quality.
    today = datetime.now(timezone(timedelta(hours=8))).date()
    start = datetime.combine(today - timedelta(days=29), datetime.min.time()) - timedelta(hours=8)
    day_key = func.date(EvalTask.created_at, "+8 hours")
    activity_rows = (await db.execute(
        select(day_key, EvalTask.status, func.count())
        .where(EvalTask.created_at >= start)
        .group_by(day_key, EvalTask.status)
    )).all()
    activity = {str(today - timedelta(days=i)): {"created": 0, "failed": 0} for i in range(29, -1, -1)}
    for day, status, count in activity_rows:
        if day in activity:
            activity[day]["created"] += int(count)
            if status in ("failed", "partial_failed"):
                activity[day]["failed"] += int(count)
    type_rows = (await db.execute(select(EvalTask.task_type, func.count()).group_by(EvalTask.task_type))).all()
    review_count = await db.scalar(select(func.count()).select_from(EvalTask).where(EvalTask.status == "pending_review")) or 0
    approval_count = await db.scalar(select(func.count()).select_from(AgentSession).where(AgentSession.status == "waiting_confirm")) or 0
    return {
        "activity": [{"date": day, **counts} for day, counts in activity.items()],
        "task_types": [{"type": kind or "unknown", "count": int(count)} for kind, count in type_rows],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "todos": todos[:15],
        "running": [{"id": t.id, "name": t.name, "status": t.status, "progress": t.progress} for t in running_rows],
        "failed": [{"id": t.id, "name": t.name, "error_message": t.error_message or ""} for t in failed_rows],
        "recent": [{
            "id": t.id,
            "name": t.name,
            "status": t.status,
            "pass_rate": t.pass_rate,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        } for t in recent],
        "status_counts": {status or "unknown": int(count) for status, count in status_rows},
        "pending_approvals": approval_count,
        "pending_reviews": review_count,
        "message": "",
    }
