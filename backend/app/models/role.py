"""RBAC - 角色与权限"""
from sqlalchemy import String, DateTime, Integer, Table, ForeignKey, Column
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.database import Base

# 角色-权限多对多
role_permission = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)  # admin, researcher, viewer
    name: Mapped[str] = mapped_column(String(100))
    data_scope: Mapped[str] = mapped_column(String(20), default="all")  # all=全部数据, own=仅自己的
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)  # dataset:create, task:list
    resource: Mapped[str] = mapped_column(String(50))  # dataset, task, model
    action: Mapped[str] = mapped_column(String(30))  # list, view, create, delete
    name: Mapped[str] = mapped_column(String(100))
