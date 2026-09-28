"""会话派生的执行者上下文（不可被请求体 tenant_id 覆盖）。"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role, User
from app.services.rbac import get_role_code, get_user_data_scope, get_user_permissions


@dataclass
class ActorContext:
    user_id: int
    username: str
    tenant_id: int
    role_code: str
    data_scope: str  # all | own | shared
    permissions: set[str] = field(default_factory=set)
    is_admin: bool = False

    def has_permission(self, code: str) -> bool:
        return code in self.permissions


async def build_actor(db: AsyncSession, user: User) -> ActorContext:
    tenant_id = int(getattr(user, "tenant_id", None) or 0)
    if not tenant_id:
        raise ValueError("user missing tenant_id")
    perms = await get_user_permissions(db, user)
    role_code = get_role_code(user)
    if getattr(user, "role_id", None) and role_code != "admin":
        r = await db.execute(select(Role).where(Role.id == user.role_id))
        role = r.scalar_one_or_none()
        if role:
            role_code = role.code
    scope = await get_user_data_scope(db, user)
    if scope not in {"all", "own", "shared"}:
        scope = "all" if role_code == "admin" else "own"
    is_admin = role_code == "admin" or getattr(user, "role", None) == "admin"
    return ActorContext(
        user_id=user.id,
        username=user.username,
        tenant_id=tenant_id,
        role_code=role_code or (getattr(user, "role", None) or "viewer"),
        data_scope=scope,
        permissions=perms,
        is_admin=is_admin,
    )


def effective_tenant_id(actor: ActorContext, claimed_tenant_id: int | str | None = None) -> int:
    """忽略客户端声称的 tenant_id，始终使用会话租户。"""
    _ = claimed_tenant_id
    return actor.tenant_id
