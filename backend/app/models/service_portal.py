"""External service contracts. Keys are stored as digests; releases are immutable mappings."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ServiceClient(Base):
    __tablename__ = "service_clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True)
    workspace_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(120))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    key_prefix: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(default=True)
    daily_tokens: Mapped[int] = mapped_column(Integer, default=100000)
    monthly_tokens: Mapped[int] = mapped_column(Integer, default=1000000)
    requests_per_minute: Mapped[int] = mapped_column(Integer, default=30)
    price_fen_per_1k: Mapped[int] = mapped_column(Integer, default=0)
    creator_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ServiceRoute(Base):
    __tablename__ = "service_routes"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True)
    workspace_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(120))
    stable_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gray_percent: Mapped[int] = mapped_column(Integer, default=0)


class ServiceRelease(Base):
    __tablename__ = "service_releases"
    __table_args__ = (UniqueConstraint("route_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(Integer, index=True)
    version: Mapped[str] = mapped_column(String(40))
    model_id: Mapped[int] = mapped_column(Integer)
    model_version_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ServiceCall(Base):
    __tablename__ = "service_calls"
    __table_args__ = (UniqueConstraint("client_id", "idempotency_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True)
    client_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    workspace_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    service_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    release_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), default="")
    reserved_tokens: Mapped[int] = mapped_column(Integer, default=0)
    price_fen_per_1k: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="accepted")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ServiceGatewayAudit(Base):
    __tablename__ = "service_gateway_audits"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    client_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(240))
    status_code: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
