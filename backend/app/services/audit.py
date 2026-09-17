"""操作审计：写入审计日志"""
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request

from app.models import AuditLog


def get_client_ip(request: Request | None) -> str:
    if not request:
        return ""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


async def log_audit(
    db: AsyncSession,
    resource: str,
    action: str,
    *,
    user_id: int | None = None,
    username: str = "",
    target_id: int | None = None,
    detail: str | None = None,
    ip: str | None = None,
):
    """记录一条审计日志。成功执行关键操作后调用。"""
    entry = AuditLog(
        user_id=user_id,
        username=username or "",
        resource=resource,
        action=action,
        target_id=target_id,
        detail=detail,
        ip=ip,
    )
    db.add(entry)
    await db.flush()
