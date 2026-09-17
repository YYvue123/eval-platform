"""操作审计 - 查询审计日志"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import AuditLog
from app.api.deps import require_permission
from app.models.user import User

router = APIRouter()


@router.get("")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    resource: str = Query("", description="资源: auth, dataset, task, model, base_model, user, role, notification"),
    action: str = Query("", description="操作: login, create, update, delete, deploy, undeploy, stop, retry 等"),
    username: str = Query("", description="操作人用户名"),
    created_at_start: str = Query("", description="开始日期 YYYY-MM-DD"),
    created_at_end: str = Query("", description="结束日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("audit:list")),
):
    q = select(AuditLog)
    if resource:
        q = q.where(AuditLog.resource == resource)
    if action:
        q = q.where(AuditLog.action == action)
    if username:
        q = q.where(AuditLog.username.contains(username))
    if created_at_start:
        q = q.where(AuditLog.created_at >= created_at_start)
    if created_at_end:
        end_val = created_at_end + " 23:59:59" if " " not in created_at_end else created_at_end
        q = q.where(AuditLog.created_at <= end_val)

    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    q = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": a.id,
                "user_id": a.user_id,
                "username": a.username or "-",
                "resource": a.resource,
                "action": a.action,
                "target_id": a.target_id,
                "detail": a.detail or "",
                "ip": a.ip or "",
                "tenant_id": getattr(a, "tenant_id", "") or "",
                "trace_id": getattr(a, "trace_id", "") or "",
                "parent_trace_id": getattr(a, "parent_trace_id", "") or "",
                "created_at": a.created_at.isoformat(),
            }
            for a in items
        ],
        "total": total or 0,
    }
