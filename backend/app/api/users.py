"""用户管理 API - RBAC 权限控制"""
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, asc, desc
from pydantic import BaseModel

from app.database import get_db
from app.models import User, Role
from app.api.deps import get_current_user, require_admin, require_permission
from app.services.rbac import get_user_permissions, get_role_code, get_user_data_scope
from app.utils.auth import get_password_hash, verify_password, validate_password_strength
from app.services.audit import log_audit, get_client_ip
from app.config import settings

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    password: str
    phone: str = ""
    email: str = ""
    role: str = "viewer"  # admin, researcher, viewer
    role_id: int | None = None


class UserUpdate(BaseModel):
    phone: str | None = None
    email: str | None = None
    role: str | None = None
    role_id: int | None = None
    password: str | None = None


async def _resolve_role_code(db: AsyncSession, u: User) -> str:
    if getattr(u, "role", None) == "admin":
        return "admin"
    if getattr(u, "role_id", None):
        r = await db.execute(select(Role).where(Role.id == u.role_id))
        ro = r.scalar_one_or_none()
        if ro:
            return ro.code
    return getattr(u, "role", None) or "viewer"


def _parse_user_sort(sort_by: str, sort_order: str):
    col_map = {"created_at": User.created_at, "username": User.username, "id": User.id, "updated_at": User.updated_at}
    col = col_map.get(sort_by, User.created_at)
    return desc(col) if sort_order.lower() == "desc" else asc(col)


@router.get("/options")
async def list_user_options(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """获取用户选项（用于下拉选择）。有 user:list 返回全部，否则仅返回当前用户"""
    perms = await get_user_permissions(db, current)
    if "user:list" in perms:
        result = await db.execute(select(User.id, User.username).order_by(User.username))
        rows = result.all()
        return [{"id": r[0], "username": r[1]} for r in rows]
    return [{"id": current.id, "username": current.username}]


@router.get("")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=500),
    search: str = Query(""),
    role_filter: str = Query("", alias="role"),
    created_by: int = Query(None, description="创建人 user_id"),
    created_at_start: str = Query("", description="创建时间起 YYYY-MM-DD"),
    created_at_end: str = Query("", description="创建时间止 YYYY-MM-DD"),
    sort_by: str = Query("created_at", description="created_at, username, id, updated_at"),
    sort_order: str = Query("desc", description="asc, desc"),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """有 user:list 返回所有用户，否则仅返回自己（个人中心）"""
    perms = await get_user_permissions(db, current)
    if "user:list" not in perms:
        rc = await _resolve_role_code(db, current)
        return {"items": [_user_to_dict(current, rc)], "total": 1}
    q = select(User)
    if search:
        q = q.where(
            or_(
                User.username.contains(search),
                User.phone.contains(search),
                User.email.contains(search),
            )
        )
    if role_filter:
        sub = select(Role.id).where(Role.code == role_filter)
        q = q.where(User.role_id.in_(sub))
    if created_by is not None:
        q = q.where(User.created_by == created_by)
    if created_at_start:
        q = q.where(User.created_at >= created_at_start)
    if created_at_end:
        end_val = created_at_end + " 23:59:59" if " " not in created_at_end else created_at_end
        q = q.where(User.created_at <= end_val)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    order_col = _parse_user_sort(sort_by, sort_order)
    q = q.offset((page - 1) * page_size).limit(page_size).order_by(order_col)
    result = await db.execute(q)
    users = result.scalars().all()
    creator_ids = {getattr(u, "created_by", None) for u in users if getattr(u, "created_by", None)}
    creator_map = {}
    if creator_ids:
        ur = await db.execute(select(User.id, User.username).where(User.id.in_(creator_ids)))
        creator_map = {r[0]: r[1] for r in ur.all()}
    items = []
    for u in users:
        rc = await _resolve_role_code(db, u)
        d = _user_to_dict(u, rc)
        d["created_by"] = getattr(u, "created_by", None)
        d["created_by_username"] = creator_map.get(getattr(u, "created_by", None), "-")
        items.append(d)
    return {"items": items, "total": total or 0}


def _user_to_dict(u: User, role_code: str | None = None) -> dict:
    d = {
        "id": u.id,
        "username": u.username,
        "phone": u.phone or "",
        "email": u.email or "",
        "role": role_code or getattr(u, "role", None) or "viewer",
        "role_id": getattr(u, "role_id", None),
        "created_at": u.created_at.isoformat(),
        "updated_at": getattr(u, "updated_at", u.created_at).isoformat() if getattr(u, "updated_at", None) else u.created_at.isoformat(),
    }
    d["avatar"] = getattr(u, "avatar", None) or ""
    d["nickname"] = getattr(u, "nickname", None) or ""
    return d


@router.get("/me")
async def get_me(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    perms = await get_user_permissions(db, current)
    scope = await get_user_data_scope(db, current)
    role_code = await _resolve_role_code(db, current)
    d = _user_to_dict(current, role_code)
    d["permissions"] = list(perms)
    d["data_scope"] = scope
    d["role_code"] = role_code
    return d


@router.get("/me/avatar")
async def get_me_avatar(
    current: User = Depends(get_current_user),
):
    """返回当前用户头像图片，无头像时 404"""
    avatar = getattr(current, "avatar", None)
    if not avatar or not avatar.strip():
        raise HTTPException(404, "未设置头像")
    path = os.path.join(settings.UPLOAD_DIR, avatar)
    if not os.path.isfile(path):
        raise HTTPException(404, "头像文件不存在")
    ext = os.path.splitext(path)[1].lower()
    media = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png" if ext == ".png" else "image/gif" if ext == ".gif" else "image/webp"
    return FileResponse(path, media_type=media)


@router.put("/me")
async def update_me(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
    phone: str = Form(""),
    email: str = Form(""),
    nickname: str = Form(""),
    old_password: str = Form(""),
    new_password: str = Form(""),
    avatar: UploadFile | None = File(None),
):
    """个人资料更新：头像、手机、邮箱、昵称、修改密码"""
    if phone is not None and phone != "":
        current.phone = phone.strip()
    if email is not None:
        current.email = email.strip() if email else ""
    if nickname is not None:
        current.nickname = nickname.strip() if nickname else None
    if current.nickname == "":
        current.nickname = None

    if new_password:
        if not old_password:
            raise HTTPException(400, "修改密码需提供原密码")
        if not verify_password(old_password, current.password_hash):
            raise HTTPException(400, "原密码错误")
        try:
            validate_password_strength(new_password)
        except ValueError as e:
            raise HTTPException(400, str(e))
        current.password_hash = get_password_hash(new_password)

    if avatar and avatar.filename:
        allowed = (".jpg", ".jpeg", ".png", ".gif", ".webp")
        ext = os.path.splitext((avatar.filename or "").lower())[1]
        if ext not in allowed:
            raise HTTPException(400, "头像仅支持 jpg/png/gif/webp")
        avatars_dir = os.path.join(settings.UPLOAD_DIR, "avatars")
        os.makedirs(avatars_dir, exist_ok=True)
        fname = f"user_{current.id}_{uuid.uuid4().hex[:8]}{ext}"
        rel_path = os.path.join("avatars", fname)
        full_path = os.path.join(settings.UPLOAD_DIR, rel_path)
        content = await avatar.read()
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(400, "头像大小不能超过 5MB")
        with open(full_path, "wb") as f:
            f.write(content)
        if getattr(current, "avatar", None):
            old_path = os.path.join(settings.UPLOAD_DIR, current.avatar)
            if os.path.isfile(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    pass
        current.avatar = rel_path.replace("\\", "/")

    await db.commit()
    await db.refresh(current)
    await log_audit(db, "user", "update", user_id=current.id, username=current.username, target_id=current.id, detail="个人资料", ip=get_client_ip(request))
    await db.commit()
    role_code = await _resolve_role_code(db, current)
    return _user_to_dict(current, role_code)


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    perms = await get_user_permissions(db, current)
    if current.id != user_id and "user:list" not in perms:
        raise HTTPException(403, "无权限查看其他用户")
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(404, "用户不存在")
    rc = await _resolve_role_code(db, u)
    d = _user_to_dict(u, rc)
    d["created_by"] = getattr(u, "created_by", None)
    d["created_by_username"] = "-"
    if getattr(u, "created_by", None):
        cr = await db.execute(select(User.username).where(User.id == u.created_by))
        r = cr.scalar_one_or_none()
        if r:
            d["created_by_username"] = r
    return d


@router.post("")
async def create_user(
    data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(400, "用户名已存在")
    try:
        validate_password_strength(data.password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    role_id = data.role_id
    if not role_id and data.role:
        r = await db.execute(select(Role).where(Role.code == data.role))
        ro = r.scalar_one_or_none()
        if ro:
            role_id = ro.id
    role_code = data.role or "viewer"
    if role_code == "admin":
        role_code = "admin"
    u = User(
        username=data.username,
        password_hash=get_password_hash(data.password),
        phone=data.phone or "",
        email=data.email or "",
        created_by=current.id,
        role=role_code,
        role_id=role_id,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    await log_audit(db, "user", "create", user_id=current.id, username=current.username, target_id=u.id, detail=u.username, ip=get_client_ip(request))
    await db.commit()
    return _user_to_dict(u, role_code)


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    data: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    perms = await get_user_permissions(db, current)
    if "user:edit" not in perms and current.id != user_id:
        raise HTTPException(403, "无权限修改其他用户")
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(404, "用户不存在")
    if "user:edit" not in perms:
        raise HTTPException(403, "无权限")
    if "user:list" not in perms:
        # 非管理员只能改自己的 phone、email、password，不能改 role
        if data.phone is not None:
            u.phone = data.phone
        if data.email is not None:
            u.email = data.email
        if data.password:
            try:
                validate_password_strength(data.password)
            except ValueError as e:
                raise HTTPException(400, str(e))
            u.password_hash = get_password_hash(data.password)
    elif "user:list" in perms:
        if data.phone is not None:
            u.phone = data.phone
        if data.email is not None:
            u.email = data.email
        if data.role is not None and data.role in ("admin", "researcher", "viewer"):
            u.role = data.role
            r = await db.execute(select(Role).where(Role.code == data.role))
            ro = r.scalar_one_or_none()
            if ro:
                u.role_id = ro.id
        if data.password:
            try:
                validate_password_strength(data.password)
            except ValueError as e:
                raise HTTPException(400, str(e))
            u.password_hash = get_password_hash(data.password)
    await db.commit()
    await db.refresh(u)
    await log_audit(db, "user", "update", user_id=current.id, username=current.username, target_id=user_id, detail=u.username, ip=get_client_ip(request))
    await db.commit()
    return _user_to_dict(u)


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_admin),
):
    if current.id == user_id:
        raise HTTPException(400, "不能删除自己")
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(404, "用户不存在")
    name = u.username
    await db.delete(u)
    await log_audit(db, "user", "delete", user_id=current.id, username=current.username, target_id=user_id, detail=name, ip=get_client_ip(request))
    await db.commit()
    return {"message": "删除成功"}
