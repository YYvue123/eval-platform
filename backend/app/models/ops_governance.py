"""运维工单、演练留痕、数据授权。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OpsTicket(Base):
    __tablename__ = "ops_tickets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40), default="general")  # incident|change|vuln|request|general
    severity: Mapped[str] = mapped_column(String(20), default="medium")  # critical|high|medium|low
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|in_progress|resolved|closed|disabled
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    reporter_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    resolution: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OpsDrillRecord(Base):
    __tablename__ = "ops_drill_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    drill_type: Mapped[str] = mapped_column(String(40), default="restore")  # release|rollback|restore|fault
    operator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str] = mapped_column(String(20), default="pass")  # pass|fail|blocked
    checklist_json: Mapped[str] = mapped_column(Text, default="[]")
    notes: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    policy_version: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DataAuthorization(Base):
    __tablename__ = "data_authorizations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_type: Mapped[str] = mapped_column(String(40), default="dataset")  # dataset|benchmark|model|prompt
    asset_ref: Mapped[str] = mapped_column(String(120), default="")
    license_spdx: Mapped[str] = mapped_column(String(80), default="")
    grantor: Mapped[str] = mapped_column(String(120), default="")
    grantee_tenant: Mapped[str] = mapped_column(String(80), default="")
    purpose: Mapped[str] = mapped_column(Text, default="")
    evidence_uri: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|expired|revoked|disabled
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # 停用不删除：disabled=True 时仅不可用于新任务绑定
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
