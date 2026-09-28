"""对象级授权：租户隔离 + data_scope（all/own/shared）。"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.actor_context import ActorContext

SENSITIVE_LEVELS = frozenset({"secret", "confidential", "restricted"})


def apply_object_scope(stmt, model, actor: ActorContext, *, creator_attr: str = "creator_id"):
    """将租户与范围过滤附加到 SQLAlchemy select。"""
    tenant_col = getattr(model, "tenant_id")
    vis_col = getattr(model, "visibility", None)
    creator_col = getattr(model, creator_attr, None)

    stmt = stmt.where(tenant_col == actor.tenant_id)

    if actor.data_scope == "all":
        if vis_col is not None and not actor.is_admin:
            stmt = stmt.where(or_(vis_col != "isolated", creator_col == actor.user_id))
        return stmt

    if actor.data_scope == "shared":
        if vis_col is None or creator_col is None:
            return stmt.where(creator_col == actor.user_id) if creator_col is not None else stmt
        return stmt.where(
            or_(
                vis_col == "shared",
                creator_col == actor.user_id,
            )
        )

    # own：本人或共享；隔离对象仅本人
    if creator_col is None:
        return stmt
    if vis_col is None:
        return stmt.where(creator_col == actor.user_id)
    return stmt.where(
        or_(
            creator_col == actor.user_id,
            and_(vis_col == "shared", vis_col != "isolated"),
        )
    )


def object_is_visible(obj, actor: ActorContext, *, creator_attr: str = "creator_id") -> bool:
    if obj is None:
        return False
    tid = getattr(obj, "tenant_id", None)
    if tid is None or int(tid) != int(actor.tenant_id):
        return False
    vis = getattr(obj, "visibility", "private") or "private"
    creator_id = getattr(obj, creator_attr, None)
    if actor.data_scope == "all":
        if vis == "isolated" and not actor.is_admin and creator_id != actor.user_id:
            return False
        return True
    if actor.data_scope == "shared":
        return vis == "shared" or creator_id == actor.user_id
    # own
    return creator_id == actor.user_id or vis == "shared"


async def get_visible_or_404(
    db: AsyncSession,
    model,
    obj_id: int,
    actor: ActorContext,
    *,
    creator_attr: str = "creator_id",
    not_found: str = "资源不存在或无权访问",
):
    obj = await db.get(model, obj_id)
    if not object_is_visible(obj, actor, creator_attr=creator_attr):
        raise HTTPException(404, not_found)
    return obj


def require_sensitive_export(actor: ActorContext, security_level: str | None):
    level = (security_level or "").lower()
    if level in SENSITIVE_LEVELS and not actor.has_permission("dataset:export_sensitive"):
        raise HTTPException(403, "需要权限: dataset:export_sensitive")
