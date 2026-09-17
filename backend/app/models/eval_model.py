from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EvalModel(Base):
    __tablename__ = "eval_models"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    model_type: Mapped[str] = mapped_column(String(50), default="llm")
    model_source: Mapped[str] = mapped_column(String(50), default="external")
    description: Mapped[str] = mapped_column(Text, default="")
    support_language: Mapped[str] = mapped_column(String(200), default="zh")
    support_modal: Mapped[str] = mapped_column(String(80), default="text")
    deploy_type: Mapped[str] = mapped_column(String(50), default="api")
    access_mode: Mapped[str] = mapped_column(String(50), default="online")
    architecture: Mapped[str] = mapped_column(String(80), default="")
    parameter_scale: Mapped[str] = mapped_column(String(50), default="")
    context_length: Mapped[int] = mapped_column(Integer, default=8192)
    applicable_scenario: Mapped[str] = mapped_column(String(200), default="")
    current_version: Mapped[str] = mapped_column(String(32), default="V1.0")
    api_url: Mapped[str] = mapped_column(String(500), default="")
    request_method: Mapped[str] = mapped_column(String(10), default="POST")
    auth_type: Mapped[str] = mapped_column(String(32), default="bearer_token")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    served_model_name: Mapped[str] = mapped_column(String(200), default="")
    timeout: Mapped[int] = mapped_column(Integer, default=60)
    retry_count: Mapped[int] = mapped_column(Integer, default=1)
    channel_type: Mapped[str] = mapped_column(String(32), default="https")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    health_status: Mapped[str] = mapped_column(String(32), default="unknown")
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ModelCallLog(Base):
    __tablename__ = "model_call_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(Integer, index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    call_status: Mapped[str] = mapped_column(String(20), default="success")
    error_message: Mapped[str] = mapped_column(Text, default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
