from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User
from app.utils.auth import decode_token
from app.services.rbac import get_user_permissions
from app.services.actor_context import ActorContext, build_actor

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期或认证无效，请重新登录"
        )
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在或已失效，请重新登录")
    if getattr(user, "status", "active") != "active":
        raise HTTPException(status_code=401, detail="用户已禁用，请联系管理员")
    if not getattr(user, "tenant_id", None):
        raise HTTPException(status_code=401, detail="用户未分配租户，请联系管理员")
    return user


def require_permission(permission: str):
    """需要指定权限的依赖，返回 User。"""

    async def _check(
        current: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        perms = await get_user_permissions(db, current)
        if permission not in perms:
            raise HTTPException(status_code=403, detail=f"需要权限: {permission}")
        return current

    return _check


def require_actor(permission: str):
    """需要指定权限，返回 ActorContext（租户与范围已绑定会话）。"""

    async def _check(
        current: User = Depends(require_permission(permission)),
        db: AsyncSession = Depends(get_db),
    ) -> ActorContext:
        try:
            return await build_actor(db, current)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    return _check


async def require_admin(current: User = Depends(get_current_user)) -> User:
    """仅 admin 角色可用"""
    if getattr(current, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current
