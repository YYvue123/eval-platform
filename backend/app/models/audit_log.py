"""操作审计日志 - 记录关键接口与行为"""
from sqlalchemy import String, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=True)  # 操作人，登录失败等可为空
    username: Mapped[str] = mapped_column(String(64), default="")  # 冗余，便于列表展示
    resource: Mapped[str] = mapped_column(String(32))   # auth, dataset, task, model, base_model, user, role, notification
    action: Mapped[str] = mapped_column(String(32))    # login, create, update, delete, deploy, undeploy, stop, retry, etc.
    target_id: Mapped[int] = mapped_column(Integer, nullable=True)  # 操作对象 ID，如 dataset_id
    detail: Mapped[str] = mapped_column(Text, nullable=True)  # 额外说明，如名称、原因
    ip: Mapped[str] = mapped_column(String(64), nullable=True)
    tenant_id: Mapped[str] = mapped_column(String(64), default="")
    trace_id: Mapped[str] = mapped_column(String(64), default="")
    parent_trace_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
