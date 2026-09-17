from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import User
from app.api.deps import require_permission

router = APIRouter()


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("dashboard:view")),
):
    user_count = await db.scalar(select(func.count()).select_from(User)) or 0
    return {
        "user_count": user_count,
        "dataset_count": 0,
        "model_count": 0,
        "task_count": 0,
        "message": "评测业务模块尚未接入，当前为平台骨架。",
    }


@router.get("/workbench")
async def get_workbench(
    _: User = Depends(require_permission("dashboard:view")),
):
    return {
        "todos": [],
        "running": [],
        "failed": [],
        "message": "评测任务工作台将在后续迭代接入。",
    }
