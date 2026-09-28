"""角色与权限管理 API - 仅管理员"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel

from app.database import get_db
from app.models import Role, Permission
from app.api.deps import require_admin, require_permission
from app.models import User
from app.models.role import role_permission
from app.services.audit import log_audit, get_client_ip
from app.services.permission_loader import RESOURCE_NAMES, load_all_permissions

router = APIRouter()


class RoleUpdate(BaseModel):
    data_scope: str | None = None  # all | own
    permission_codes: list[str] | None = None  # 完整权限列表，替换原有


@router.get("")
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("role:list")),
):
    """角色列表"""
    r = await db.execute(select(Role).order_by(Role.id))
    items = r.scalars().all()
    return [{"id": ro.id, "code": ro.code, "name": ro.name, "data_scope": ro.data_scope} for ro in items]


@router.get("/permissions")
async def list_permissions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("role:list")),
):
    """权限列表（按资源分组，从配置+扫描自动加载）"""
    perms = [{"code": f"{r}:{a}", "resource": r, "action": a, "name": n} for r, a, n in load_all_permissions()]
    # 按 resource 分组
    by_resource = {}
    for p in perms:
        res = p["resource"]
        if res not in by_resource:
            by_resource[res] = {"resource": res, "resourceName": _resource_name(res), "actions": []}
        by_resource[res]["actions"].append(p)
    return list(by_resource.values())


def _resource_name(resource: str) -> str:
    return RESOURCE_NAMES.get(resource, resource)


@router.get("/{role_id}")
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("role:view")),
):
    """角色详情（含权限列表）"""
    r = await db.execute(select(Role).where(Role.id == role_id))
    ro = r.scalar_one_or_none()
    if not ro:
        raise HTTPException(404, "角色不存在")
    perms = await db.execute(
        select(Permission.code)
        .join(role_permission, Permission.id == role_permission.c.permission_id)
        .where(role_permission.c.role_id == role_id)
    )
    codes = [p[0] for p in perms.all()]
    return {
        "id": ro.id,
        "code": ro.code,
        "name": ro.name,
        "data_scope": ro.data_scope or "all",
        "permission_codes": codes,
    }


@router.put("/{role_id}")
async def update_role(
    role_id: int,
    data: RoleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("role:edit")),
):
    """更新角色：数据范围、权限配置"""
    r = await db.execute(select(Role).where(Role.id == role_id))
    ro = r.scalar_one_or_none()
    if not ro:
        raise HTTPException(404, "角色不存在")
    if ro.code == "admin":
        raise HTTPException(400, "管理员角色不可修改")

    if data.data_scope is not None:
        if data.data_scope not in ("all", "own", "shared"):
            raise HTTPException(400, "data_scope 必须为 all、own 或 shared")
        ro.data_scope = data.data_scope

    if data.permission_codes is not None:
        # 删除原有，插入新的
        await db.execute(delete(role_permission).where(role_permission.c.role_id == role_id))
        all_perms = await db.execute(select(Permission))
        perm_map = {p.code: p.id for p in all_perms.scalars().all()}
        for code in data.permission_codes:
            if code in perm_map:
                await db.execute(
                    role_permission.insert().values(role_id=role_id, permission_id=perm_map[code])
                )
    await db.commit()
    await log_audit(db, "role", "update", user_id=current.id, username=getattr(current, "username", ""), target_id=role_id, detail=ro.name, ip=get_client_ip(request))
    await db.commit()
    return {"message": "更新成功"}
