from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
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
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_url: Mapped[str] = mapped_column(String(500), default="")
    request_method: Mapped[str] = mapped_column(String(10), default="POST")
    auth_type: Mapped[str] = mapped_column(String(32), default="bearer_token")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    served_model_name: Mapped[str] = mapped_column(String(200), default="")
    timeout: Mapped[int] = mapped_column(Integer, default=60)
    retry_count: Mapped[int] = mapped_column(Integer, default=1)
    channel_type: Mapped[str] = mapped_column(String(32), default="https")
    request_template: Mapped[str] = mapped_column(Text, default="")
    response_mapping: Mapped[str] = mapped_column(Text, default="")
    scene_white_list: Mapped[str] = mapped_column(Text, default="[]")
    parallel_limit: Mapped[int] = mapped_column(Integer, default=4)
    support_stream: Mapped[bool] = mapped_column(Boolean, default=False)
    probe_interval_sec: Mapped[int] = mapped_column(Integer, default=300)
    consecutive_fail: Mapped[int] = mapped_column(Integer, default=0)
    circuit_open_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    health_status: Mapped[str] = mapped_column(String(32), default="unknown")
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ModelMeta(Base):
    __tablename__ = "model_metas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("eval_models.id"), unique=True, index=True)
    train_data_desc: Mapped[str] = mapped_column(Text, default="")
    finetune_method: Mapped[str] = mapped_column(String(80), default="")
    infer_framework: Mapped[str] = mapped_column(String(80), default="")
    hardware: Mapped[str] = mapped_column(String(120), default="")
    company_name: Mapped[str] = mapped_column(String(120), default="")
    company_model_code: Mapped[str] = mapped_column(String(120), default="")
    contact_name: Mapped[str] = mapped_column(String(80), default="")
    contact_email: Mapped[str] = mapped_column(String(120), default="")
    source_type: Mapped[str] = mapped_column(String(32), default="")
    base_model: Mapped[str] = mapped_column(String(120), default="")
    deploy_cluster: Mapped[str] = mapped_column(String(120), default="")
    industry: Mapped[str] = mapped_column(String(50), default="")


class ModelCost(Base):
    __tablename__ = "model_costs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    token_price_per_1k: Mapped[float] = mapped_column(Float, default=0.002)
    latency_price_per_sec: Mapped[float] = mapped_column(Float, default=0.01)
    gpu_hour_price: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("eval_models.id"), index=True)
    version_code: Mapped[str] = mapped_column(String(32))
    version_desc: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="available")
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ModelAccessConfig(Base):
    __tablename__ = "model_access_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("eval_models.id"), index=True)
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_url: Mapped[str] = mapped_column(String(500), default="")
    request_method: Mapped[str] = mapped_column(String(10), default="POST")
    auth_type: Mapped[str] = mapped_column(String(32), default="bearer_token")
    auth_config: Mapped[str] = mapped_column(Text, default="{}")
    request_template: Mapped[str] = mapped_column(Text, default="")
    response_mapping: Mapped[str] = mapped_column(Text, default="")
    timeout: Mapped[int] = mapped_column(Integer, default=60)
    retry_count: Mapped[int] = mapped_column(Integer, default=1)
    channel_type: Mapped[str] = mapped_column(String(32), default="https")


class ModelAcl(Base):
    __tablename__ = "model_acls"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("eval_models.id"), index=True)
    principal_type: Mapped[str] = mapped_column(String(20), default="user")
    principal_id: Mapped[int] = mapped_column(Integer, default=0)
    action: Mapped[str] = mapped_column(String(20), default="invoke")
    allow: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ModelHealthSample(Base):
    __tablename__ = "model_health_samples"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(Integer, index=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
