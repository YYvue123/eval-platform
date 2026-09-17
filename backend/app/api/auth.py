from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User
from app.utils.auth import verify_password, get_password_hash, create_access_token
from app.services.audit import log_audit, get_client_ip

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str = "user"


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token({"sub": user.username})
    from app.models import Role
    role = getattr(user, "role", None) or "viewer"
    if getattr(user, "role_id", None):
        r = await db.execute(select(Role).where(Role.id == user.role_id))
        ro = r.scalar_one_or_none()
        if ro:
            role = ro.code
    await log_audit(db, "auth", "login", user_id=user.id, username=user.username, ip=get_client_ip(request))
    await db.commit()
    return TokenResponse(access_token=token, username=user.username, role=role)


@router.post("/register")
async def register(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(username=data.username, password_hash=get_password_hash(data.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await log_audit(db, "auth", "register", user_id=user.id, username=user.username, ip=get_client_ip(request))
    await db.commit()
    return {"message": "注册成功"}
