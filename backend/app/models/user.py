from sqlalchemy import String, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(20), default="user")  # 兼容旧数据
    role_id: Mapped[int] = mapped_column(Integer, nullable=True)  # FK -> roles.id
    avatar: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)  # 头像路径，如 avatars/xxx.jpg
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    created_by: Mapped[int] = mapped_column(Integer, nullable=True)  # 创建者 user_id
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
