"""Tenant-scoped leaderboard policy, immutable publications and review decisions."""
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class LeaderboardDemo(Base):
    """Synthetic presentation payloads. Never evaluation results or publications."""
    __tablename__ = 'leaderboard_demo_payloads'
    __table_args__ = (UniqueConstraint('tenant_id', 'category'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[str] = mapped_column(Text)
    creator_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LeaderboardPolicy(Base):
    __tablename__ = 'leaderboard_policies'
    __table_args__ = (UniqueConstraint('tenant_id', 'cohort_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True)
    cohort_id: Mapped[str] = mapped_column(String(200))
    weights_json: Mapped[str] = mapped_column(Text, default='{}')
    updated_by: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LeaderboardPublication(Base):
    __tablename__ = 'leaderboard_publications'
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True)
    cohort_id: Mapped[str] = mapped_column(String(200), index=True)
    board: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default='published')
    payload_json: Mapped[str] = mapped_column(Text)
    public_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    creator_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    withdrawal_reason: Mapped[str] = mapped_column(String(500), default='')


class LeaderboardReview(Base):
    __tablename__ = 'leaderboard_reviews'
    __table_args__ = (UniqueConstraint('tenant_id', 'task_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    reason: Mapped[str] = mapped_column(String(500))
    decision_note: Mapped[str] = mapped_column(String(500), default='')
    reporter_id: Mapped[int] = mapped_column(Integer)
    reviewer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
