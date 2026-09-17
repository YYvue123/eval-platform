"""RBAC 权限定义与工具"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Role, Permission
from app.models.role import role_permission


def _get_permissions():
    try:
        from app.services.permission_loader import load_all_permissions
        return load_all_permissions()
    except Exception:
        return _PERMISSIONS_FALLBACK


_PERMISSIONS_FALLBACK = [
    ("dashboard", "view", "工作台查看"),
    ("user", "list", "用户列表"),
    ("user", "view", "用户详情"),
    ("user", "create", "用户创建"),
    ("user", "edit", "用户编辑"),
    ("user", "delete", "用户删除"),
    ("notification", "list", "通知管理"),
    ("notification", "create", "通知发送"),
    ("notification", "delete", "通知删除"),
    ("notification", "view_mine", "我的通知"),
    ("role", "list", "角色列表"),
    ("role", "view", "角色详情"),
    ("role", "edit", "角色权限配置"),
    ("audit", "list", "操作审计"),
]


def _admin_permissions():
    return [f"{r}:{a}" for r, a, _ in _get_permissions()]


RESEARCHER_PERMISSIONS = [
    "dashboard:view",
    "notification:view_mine",
    "dataset:list", "dataset:view", "dataset:create", "dataset:edit", "dataset:export",
    "model:list", "model:view", "model:create", "model:edit", "model:invoke",
    "prompt:list", "prompt:view", "prompt:create", "prompt:edit", "prompt:publish",
    "resource:list", "resource:view", "resource:invoke",
    "quality:list", "quality:view", "quality:run", "quality:edit",
    "task:list", "task:view", "task:create", "task:edit", "task:run",
    "leaderboard:view",
    "service:list", "service:view", "service:create",
    "agent:list", "agent:view", "agent:invoke", "agent:confirm",
    "ops:view",
]

VIEWER_PERMISSIONS = [
    "dashboard:view",
    "notification:view_mine",
    "dataset:list", "dataset:view",
    "model:list", "model:view",
    "prompt:list", "prompt:view",
    "resource:list", "resource:view",
    "quality:list", "quality:view",
    "task:list", "task:view",
    "leaderboard:view",
    "service:list", "service:view",
    "agent:list", "agent:view",
    "ops:view",
]

USER_SELF_PERMISSIONS = ["user:view"]


async def get_user_permissions(db: AsyncSession, user: User) -> set[str]:
    if getattr(user, "role", None) == "admin":
        return set(_admin_permissions())
    role = None
    if getattr(user, "role_id", None):
        r = await db.execute(select(Role).where(Role.id == user.role_id))
        role = r.scalar_one_or_none()
    if not role and getattr(user, "role", None):
        r = await db.execute(select(Role).where(Role.code == user.role))
        role = r.scalar_one_or_none()
    if not role:
        return set(VIEWER_PERMISSIONS) | set(USER_SELF_PERMISSIONS)
    if role.code == "admin":
        return set(_admin_permissions())
    perms = await db.execute(
        select(Permission.code)
        .select_from(Permission)
        .join(role_permission, Permission.id == role_permission.c.permission_id)
        .where(role_permission.c.role_id == role.id)
    )
    codes = {p[0] for p in perms.all()}
    codes.update(USER_SELF_PERMISSIONS)
    return codes


def get_role_code(user: User) -> str:
    if getattr(user, "role", None) == "admin":
        return "admin"
    return getattr(user, "role", "viewer") or "viewer"


async def get_user_data_scope(db: AsyncSession, user: User) -> str:
    if getattr(user, "role", None) == "admin":
        return "all"
    role = None
    if getattr(user, "role_id", None):
        r = await db.execute(select(Role).where(Role.id == user.role_id))
        role = r.scalar_one_or_none()
    if not role and getattr(user, "role", None):
        r = await db.execute(select(Role).where(Role.code == user.role))
        role = r.scalar_one_or_none()
    if not role:
        return "all"
    return role.data_scope or "all"
