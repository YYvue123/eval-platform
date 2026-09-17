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
    recent = (await db.execute(select(EvalTask).order_by(EvalTask.id.desc()).limit(8))).scalars().all()
    running = [t for t in recent if t.status in {"queued", "running"}]
    failed = [t for t in recent if t.status == "failed"]
    return {
        "todos": [],
        "running": [{"id": t.id, "name": t.name, "status": t.status, "progress": t.progress} for t in running],
        "failed": [{"id": t.id, "name": t.name, "error_message": t.error_message} for t in failed],
        "recent": [{"id": t.id, "name": t.name, "status": t.status, "pass_rate": t.pass_rate} for t in recent],
        "message": "",
    }
