"""系统通知 - 支持单发和广播"""
from sqlalchemy import String, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=True)  # null = 广播给所有用户
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(String(1000), default="")
    type: Mapped[str] = mapped_column(String(20), default="info")  # info | success | warning | error
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NotificationRead(Base):
    """用户已读记录 - 一条通知对多用户"""
    __tablename__ = "notification_reads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    notification_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    read_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
