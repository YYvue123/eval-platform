from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User
from app.utils.auth import decode_token
from app.services.rbac import get_user_permissions

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
    return user


def require_permission(permission: str):
    """需要指定权限的依赖"""

    async def _check(
        current: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        perms = await get_user_permissions(db, current)
        if permission not in perms:
            raise HTTPException(status_code=403, detail=f"需要权限: {permission}")
        return current

    return _check


async def require_admin(current: User = Depends(get_current_user)) -> User:
    """仅 admin 角色可用"""
    from app.services.rbac import get_role_code
    # 需要 db 来解析 role_id，这里简化用 role 字段
    if getattr(current, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current
