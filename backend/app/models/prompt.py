from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    prompt_type: Mapped[str] = mapped_column(String(50), default="eval")
    applicable_task: Mapped[str] = mapped_column(String(80), default="qa")
    applicable_model: Mapped[str] = mapped_column(String(80), default="")
    applicable_scene: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    current_version: Mapped[str] = mapped_column(String(32), default="V1.0")
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    tags: Mapped[str] = mapped_column(Text, default="[]")
    constraints: Mapped[str] = mapped_column(Text, default="")
    review_comment: Mapped[str] = mapped_column(Text, default="")
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompt_templates.id"), index=True)
    version_code: Mapped[str] = mapped_column(String(32))
    prompt_content: Mapped[str] = mapped_column(Text, default="")
    variable_config: Mapped[str] = mapped_column(Text, default="[]")
    output_format: Mapped[str] = mapped_column(String(50), default="text")
    change_desc: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PromptCallLog(Base):
    __tablename__ = "prompt_call_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prompt_id: Mapped[int] = mapped_column(Integer, index=True)
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operator: Mapped[str] = mapped_column(String(80), default="")
    operation: Mapped[str] = mapped_column(String(32), default="call")
    result: Mapped[str] = mapped_column(String(20), default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PromptTestRun(Base):
    __tablename__ = "prompt_test_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prompt_id: Mapped[int] = mapped_column(Integer, index=True)
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compare_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="done")
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[float] = mapped_column(Float, default=0)
    compare_avg_score: Mapped[float] = mapped_column(Float, default=0)
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PromptExperiment(Base):
    __tablename__ = "prompt_experiments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prompt_id: Mapped[int] = mapped_column(Integer, index=True)
    baseline_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # dataset version
    holdout_ratio: Mapped[float] = mapped_column(Float, default=0.3)
    token_budget: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft|running|done|rejected_publish
    develop_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    holdout_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    pair_stats_json: Mapped[str] = mapped_column(Text, default="{}")
    publish_recommended: Mapped[int] = mapped_column(Integer, default=0)  # 0/1
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
