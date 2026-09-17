"""操作审计：写入审计日志"""
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request

from app.models import AuditLog

_trace_ctx: ContextVar[dict] = ContextVar("audit_trace", default={})


def set_audit_trace(tenant_id: str = "", trace_id: str = "", parent_trace_id: str = "") -> None:
    _trace_ctx.set({"tenant_id": tenant_id or "", "trace_id": trace_id or "", "parent_trace_id": parent_trace_id or ""})


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
    tenant_id: str = "",
    trace_id: str = "",
    parent_trace_id: str = "",
):
    """记录一条审计日志。成功执行关键操作后调用。"""
    ctx = _trace_ctx.get() or {}
    entry = AuditLog(
        user_id=user_id,
        username=username or "",
        resource=resource,
        action=action,
        target_id=target_id,
        detail=detail,
        ip=ip,
        tenant_id=tenant_id or ctx.get("tenant_id") or "",
        trace_id=trace_id or ctx.get("trace_id") or "",
        parent_trace_id=parent_trace_id or ctx.get("parent_trace_id") or "",
    )
    db.add(entry)
    await db.flush()
