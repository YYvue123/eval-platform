from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EvalTask(Base):
    __tablename__ = "eval_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    task_type: Mapped[str] = mapped_column(String(50), default="capability")
    scene: Mapped[str] = mapped_column(String(80), default="qa")
    industry: Mapped[str] = mapped_column(String(50), default="general")
    dataset_id: Mapped[int] = mapped_column(Integer, index=True)
    dataset_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_id: Mapped[int] = mapped_column(Integer, index=True)
    prompt_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    judge_resource_id: Mapped[str] = mapped_column(String(120), default="builtin/exact_match")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    skip_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[float] = mapped_column(Float, default=0)
    pass_rate: Mapped[float] = mapped_column(Float, default=0)
    snapshot_id: Mapped[str] = mapped_column(String(64), default="")
    batch_id: Mapped[str] = mapped_column(String(64), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    report_summary: Mapped[str] = mapped_column(Text, default="")
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("eval_tasks.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_no: Mapped[int] = mapped_column(Integer, default=0)
    input_content: Mapped[str] = mapped_column(Text, default="")
    model_output: Mapped[str] = mapped_column(Text, default="")
    reference_answer: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float, default=0)
    passed: Mapped[bool] = mapped_column(default=False)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str] = mapped_column(Text, default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QualityReport(Base):
    __tablename__ = "quality_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(Integer, index=True)
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="done")
    score: Mapped[float] = mapped_column(Float, default=0)
    report_json: Mapped[str] = mapped_column(Text, default="{}")
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EvalServiceRequest(Base):
    __tablename__ = "eval_service_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(50), default="general")
    requirement: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="submitted")
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report_summary: Mapped[str] = mapped_column(Text, default="")
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
