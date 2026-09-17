"""通知管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, asc, desc
from pydantic import BaseModel

from app.database import get_db
from app.models import Notification, NotificationRead, User
from app.api.deps import get_current_user, require_permission
from app.services.audit import log_audit, get_client_ip

router = APIRouter()


class NotificationCreate(BaseModel):
    title: str
    message: str = ""
    type: str = "info"  # info | success | warning | error
    user_id: int | None = None  # null = 广播给所有用户


# ---------- 用户侧：我的通知 ----------
@router.get("/mine")
async def list_my_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:view_mine")),
):
    """当前用户收到的通知：发给自己的 + 广播的，按时间倒序"""
    uid = current_user.id
    # 子查询：我收到的 = user_id is null (广播) or user_id = uid
    subq = select(Notification).where(
        (Notification.user_id.is_(None)) | (Notification.user_id == uid)
    ).order_by(Notification.created_at.desc()).subquery()
    total = await db.scalar(select(func.count()).select_from(subq))
    q = select(Notification).where(
        (Notification.user_id.is_(None)) | (Notification.user_id == uid)
    ).order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    items = result.scalars().all()
    # 查已读（从 notification_reads 表持久化，跨设备/浏览器同步）
    read_ids = set()
    if items:
        rid_result = await db.execute(
            select(NotificationRead.notification_id).where(
                NotificationRead.user_id == uid,
                NotificationRead.notification_id.in_([n.id for n in items])
            )
        )
        read_ids = {int(r[0]) for r in rid_result.all()}
    return {
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "type": n.type,
                "read": n.id in read_ids,
                "created_at": n.created_at.isoformat(),
            }
            for n in items
        ],
        "total": total or 0,
    }


@router.get("/mine/unread-count")
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:view_mine")),
):
    """未读数量"""
    uid = current_user.id
    ids_result = await db.execute(select(Notification.id).where(
        (Notification.user_id.is_(None)) | (Notification.user_id == uid)
    ))
    all_ids = [r[0] for r in ids_result.all()]
    total = len(all_ids)
    read_count = 0
    if all_ids:
        rc = await db.scalar(
            select(func.count()).select_from(NotificationRead).where(
                NotificationRead.user_id == uid,
                NotificationRead.notification_id.in_(all_ids)
            )
        )
        read_count = rc or 0
    return {"count": max(0, total - read_count)}


@router.post("/mine/{notification_id}/read")
async def mark_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:view_mine")),
):
    """标记单条为已读"""
    uid = current_user.id
    r = await db.execute(select(Notification).where(Notification.id == notification_id))
    n = r.scalar_one_or_none()
    if not n:
        raise HTTPException(404, "通知不存在")
    if n.user_id is not None and n.user_id != uid:
        raise HTTPException(403, "无权操作此通知")
    existing = await db.execute(
        select(NotificationRead).where(
            NotificationRead.notification_id == notification_id,
            NotificationRead.user_id == uid
        )
    )
    if not existing.scalar_one_or_none():
        db.add(NotificationRead(notification_id=notification_id, user_id=uid))
        await db.commit()
    return {"message": "ok"}


@router.post("/mine/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:view_mine")),
):
    """全部标为已读"""
    uid = current_user.id
    result = await db.execute(select(Notification.id).where(
        (Notification.user_id.is_(None)) | (Notification.user_id == uid)
    ))
    ids = [r[0] for r in result.all()]
    if not ids:
        return {"message": "ok"}
    read_result = await db.execute(
        select(NotificationRead.notification_id).where(
            NotificationRead.user_id == uid,
            NotificationRead.notification_id.in_(ids)
        )
    )
    read_ids = set(r[0] for r in read_result.all())
    for nid in ids:
        if nid not in read_ids:
            db.add(NotificationRead(notification_id=nid, user_id=uid))
    await db.commit()
    return {"message": "ok"}


def _parse_notif_sort(sort_by: str, sort_order: str):
    col_map = {"created_at": Notification.created_at, "title": Notification.title, "type": Notification.type, "id": Notification.id}
    col = col_map.get(sort_by, Notification.created_at)
    return desc(col) if sort_order.lower() == "desc" else asc(col)


# ---------- 管理员：配置与管理 ----------
@router.get("")
async def list_all_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: str = Query("", description="搜索标题或内容"),
    type_filter: str = Query("", alias="type", description="类型筛选: info, success, warning, error"),
    target_filter: str = Query("", alias="target", description="目标: all=广播, user=指定用户"),
    created_at_start: str = Query("", description="创建时间起 YYYY-MM-DD"),
    created_at_end: str = Query("", description="创建时间止 YYYY-MM-DD"),
    sort_by: str = Query("created_at", description="created_at, title, type, id"),
    sort_order: str = Query("desc", description="asc, desc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:list")),
):
    """管理员：全部通知列表"""
    q = select(Notification)
    if search:
        q = q.where(or_(Notification.title.contains(search), Notification.message.contains(search)))
    if type_filter:
        q = q.where(Notification.type == type_filter)
    if target_filter == "all":
        q = q.where(Notification.user_id.is_(None))
    elif target_filter == "user":
        q = q.where(Notification.user_id.isnot(None))
    if created_at_start:
        q = q.where(Notification.created_at >= created_at_start)
    if created_at_end:
        end_val = created_at_end + " 23:59:59" if " " not in created_at_end else created_at_end
        q = q.where(Notification.created_at <= end_val)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    q = q.order_by(_parse_notif_sort(sort_by, sort_order)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    items = result.scalars().all()
    return {
        "items": [
            {
                "id": n.id,
                "user_id": n.user_id,
                "title": n.title,
                "message": n.message,
                "type": n.type,
                "created_at": n.created_at.isoformat(),
            }
            for n in items
        ],
        "total": total or 0,
    }


@router.post("")
async def create_notification(
    data: NotificationCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:create")),
):
    """管理员：创建/发送通知"""
    if data.type not in ("info", "success", "warning", "error"):
        data.type = "info"
    n = Notification(
        title=data.title,
        message=data.message or "",
        type=data.type,
        user_id=data.user_id,
    )
    db.add(n)
    await db.commit()
    await db.refresh(n)
    await log_audit(db, "notification", "create", user_id=current_user.id, username=getattr(current_user, "username", ""), target_id=n.id, detail=data.title, ip=get_client_ip(request))
    await db.commit()
    return {"id": n.id, "message": "发送成功"}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:delete")),
):
    """管理员：删除通知"""
    r = await db.execute(select(Notification).where(Notification.id == notification_id))
    n = r.scalar_one_or_none()
    if not n:
        raise HTTPException(404, "通知不存在")
    title = n.title
    await db.delete(n)
    await log_audit(db, "notification", "delete", user_id=current_user.id, username=getattr(current_user, "username", ""), target_id=notification_id, detail=title, ip=get_client_ip(request))
    await db.commit()
    return {"message": "删除成功"}
