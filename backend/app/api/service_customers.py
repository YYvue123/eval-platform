"""Customer administration and tenant-scoped evaluation operation history."""
from datetime import datetime, timezone
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.api.deps import require_permission
from app.database import get_db
from app.models import AuditLog, EvalWorkspace, ServiceClient, ServiceGatewayAudit, Tenant, TenantMembership, User
from app.services.audit import log_audit
from app.services.rbac import get_user_permissions
from app.utils.auth import get_password_hash, validate_password_strength

router = APIRouter()


class CustomerUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120, pattern=r"\S")
    status: str = Field(pattern=r"^(active|disabled)$")


class MemberCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=72)


class MemberUpdate(BaseModel):
    nickname: str = Field(default="", max_length=50)
    email: str = Field(default="", max_length=255)
    phone: str = Field(default="", max_length=20)
    status: str = Field(pattern=r"^(active|disabled)$")


class PasswordBody(BaseModel):
    password: str = Field(min_length=12, max_length=72)


def password_hash(password):
    try:
        validate_password_strength(password)
        if len(password.encode("utf-8")) > 72:
            raise ValueError("密码 UTF-8 长度不能超过 72 字节")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return get_password_hash(password)


def member_out(u):
    return {"id": u.id, "username": u.username, "nickname": u.nickname or "",
            "email": u.email, "phone": u.phone, "status": u.status,
            "created_at": u.created_at.isoformat()}


async def customer_for(db, tid):
    tenant = await db.get(Tenant, tid)
    if not tenant or not tenant.code.startswith("customer-") or tenant.status == "deleted":
        raise HTTPException(404, "客户企业不存在")
    return tenant


async def manageable_member(db, uid, tid, current):
    u = await db.get(User, uid)
    if not u or u.tenant_id != tid or u.role != "customer" or u.role_id or u.status == "deleted":
        raise HTTPException(404, "可管理的企业成员不存在")
    if u.id == current.id:
        raise HTTPException(400, "请在个人中心管理自己的账号")
    return u


async def record(db, current, tid, action, target, detail=""):
    await log_audit(db, "service", action, user_id=current.id, username=current.username,
                    tenant_id=str(tid), target_id=target, detail=detail)


@router.get("/customers")
async def customers(db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    rows = (await db.scalars(select(Tenant).where(Tenant.code.startswith("customer-"),
        Tenant.status != "deleted").order_by(Tenant.id.desc()))).all()
    counts = dict((await db.execute(select(User.tenant_id, func.count()).where(
        User.role == "customer", User.status != "deleted").group_by(User.tenant_id))).all())
    return {"items": [{"id": t.id, "name": t.name, "status": t.status,
        "member_count": counts.get(t.id, 0), "created_at": t.created_at.isoformat()} for t in rows]}


@router.put("/customers/{tid}")
async def update_customer(tid: int, body: CustomerUpdate, db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    t = await customer_for(db, tid)
    t.name, t.status = body.name.strip(), body.status
    await record(db, current, tid, "customer_update", tid, t.name)
    return {"id": tid}


@router.delete("/customers/{tid}")
async def delete_customer(tid: int, db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    t = await customer_for(db, tid)
    t.status = "deleted"
    await record(db, current, tid, "customer_delete", tid, t.name)
    # Keep identity and historical evaluation assets for billing/audit attribution.
    return {"id": tid}


@router.get("/customers/{tid}/members")
async def customer_members(tid: int, db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    await customer_for(db, tid)
    rows = (await db.scalars(select(User).where(User.tenant_id == tid, User.role == "customer")
        .order_by(User.id))).all()
    return {"items": [member_out(u) for u in rows]}


@router.post("/customers/{tid}/members")
async def add_customer_member(tid: int, body: MemberCreate, db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    t = await customer_for(db, tid)
    if t.status != "active":
        raise HTTPException(409, "请先启用企业后再添加成员")
    if await db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(409, "用户名不可用")
    u = User(username=body.username, password_hash=password_hash(body.password),
        role="customer", tenant_id=tid, created_by=current.id)
    db.add(u)
    await db.flush()
    db.add(TenantMembership(tenant_id=tid, user_id=u.id))
    await record(db, current, tid, "member_create", u.id, u.username)
    return member_out(u)


@router.put("/customers/{tid}/members/{uid}")
async def edit_customer_member(tid: int, uid: int, body: MemberUpdate, db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    await customer_for(db, tid)
    u = await manageable_member(db, uid, tid, current)
    for key, value in body.model_dump().items():
        setattr(u, key, value.strip())
    await record(db, current, tid, "member_update", uid, u.username)
    return member_out(u)


@router.post("/customers/{tid}/members/{uid}/password")
async def reset_customer_password(tid: int, uid: int, body: PasswordBody, db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    await customer_for(db, tid)
    u = await manageable_member(db, uid, tid, current)
    u.password_hash = password_hash(body.password)
    await record(db, current, tid, "member_password", uid, u.username)
    return {"id": uid}


@router.delete("/customers/{tid}/members/{uid}")
async def remove_customer_member(tid: int, uid: int, db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    await customer_for(db, tid)
    u = await manageable_member(db, uid, tid, current)
    u.status = "deleted"
    await record(db, current, tid, "member_delete", uid, u.username)
    return {"id": uid}


@router.get("/customers/{tid}/clients")
async def customer_clients(tid: int, db=Depends(get_db), current=Depends(require_permission("service:admit"))):
    await customer_for(db, tid)
    rows = (await db.execute(select(ServiceClient, EvalWorkspace.name).outerjoin(
        EvalWorkspace, EvalWorkspace.id == ServiceClient.workspace_id).where(ServiceClient.tenant_id == tid))).all()
    return {"items": [{"id": c.id, "name": c.name, "workspace_name": name, "active": c.active,
        "daily_tokens": c.daily_tokens, "monthly_tokens": c.monthly_tokens,
        "requests_per_minute": c.requests_per_minute, "price_fen_per_1k": c.price_fen_per_1k} for c, name in rows]}


@router.get("/records")
async def operation_records(tenant_id: int | None = None, member_id: int | None = None,
    action: str = "", start: datetime | None = None, end: datetime | None = None,
    source: Literal["operations", "gateway"] = "operations",
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db), current=Depends(require_permission("service:records"))):
    tid = tenant_id or current.tenant_id
    if tid != current.tenant_id:
        if "service:admit" not in await get_user_permissions(db, current):
            raise HTTPException(403, "无权查看其他企业的操作记录")
        await customer_for(db, tid)
    if member_id is not None:
        member = await db.get(User, member_id)
        if not member or member.tenant_id != tid:
            raise HTTPException(404, "企业成员不存在")
    def utc(value):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    if start and end and utc(start) > utc(end):
        raise HTTPException(400, "开始时间不能晚于结束时间")
    if source == "gateway":
        q = select(ServiceGatewayAudit, ServiceClient.name, User.username).join(
            ServiceClient, ServiceClient.id == ServiceGatewayAudit.client_id).outerjoin(
            User, User.id == ServiceClient.creator_id).where(
            ServiceGatewayAudit.tenant_id == tid, ServiceClient.tenant_id == tid)
        if member_id is not None:
            q = q.where(ServiceClient.creator_id == member_id)
        if start:
            q = q.where(ServiceGatewayAudit.created_at >= utc(start))
        if end:
            q = q.where(ServiceGatewayAudit.created_at <= utc(end))
        total = await db.scalar(select(func.count()).select_from(q.subquery()))
        rows = (await db.execute(q.order_by(ServiceGatewayAudit.id.desc()).offset((page - 1) * page_size).limit(page_size))).all()
        return {"total": total, "items": [{"id": a.id, "username": username or "已删除成员",
            "resource": "gateway", "action": a.method, "target_id": a.client_id,
            "detail": json.dumps({"client_name": name, "request_path": a.path, "http_status": a.status_code}, ensure_ascii=False),
            "created_at": a.created_at.isoformat() + "Z"} for a, name, username in rows]}
    q = select(AuditLog, User.username).outerjoin(User, User.id == AuditLog.user_id).where(
        AuditLog.resource.in_(["service", "task"]), or_(User.tenant_id == tid,
            (AuditLog.tenant_id == str(tid)) & (User.role != "customer") &
            (AuditLog.resource == "service") & AuditLog.action.in_([
                "customer_create", "customer_update", "customer_delete", "member_create",
                "member_update", "member_delete", "member_password", "quota", "asset_grant"])))
    if member_id is not None:
        q = q.where(AuditLog.user_id == member_id)
    if action:
        q = q.where(AuditLog.action == action)
    if start:
        q = q.where(AuditLog.created_at >= utc(start))
    if end:
        q = q.where(AuditLog.created_at <= utc(end))
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    return {"total": total, "items": [{"id": a.id, "user_id": a.user_id,
        "username": a.username or name or "系统", "resource": a.resource, "action": a.action,
        "target_id": a.target_id, "detail": a.detail or "", "created_at": a.created_at.isoformat() + "Z"}
        for a, name in rows]}
