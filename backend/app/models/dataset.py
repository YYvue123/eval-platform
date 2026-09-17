from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    dataset_type: Mapped[str] = mapped_column(String(50), default="qa")
    task_type: Mapped[str] = mapped_column(String(50), default="qa")
    domain_type: Mapped[str] = mapped_column(String(50), default="general")
    data_source: Mapped[str] = mapped_column(String(50), default="upload")
    data_format: Mapped[str] = mapped_column(String(20), default="json")
    data_count: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text, default="")
    current_version: Mapped[str] = mapped_column(String(32), default="V1.0")
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_status: Mapped[str] = mapped_column(String(32), default="unchecked")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    tags: Mapped[str] = mapped_column(Text, default="[]")
    security_level: Mapped[str] = mapped_column(String(32), default="internal")
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), index=True)
    version_code: Mapped[str] = mapped_column(String(32))
    version_desc: Mapped[str] = mapped_column(Text, default="")
    change_content: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(String(500), default="")
    data_count: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str] = mapped_column(String(64), default="")
    quality_score: Mapped[float | None] = mapped_column(nullable=True)
    quality_status: Mapped[str] = mapped_column(String(32), default="unchecked")
    status: Mapped[str] = mapped_column(String(32), default="available")
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DatasetItem(Base):
    __tablename__ = "dataset_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id"), index=True)
    item_no: Mapped[int] = mapped_column(Integer, default=0)
    input_content: Mapped[str] = mapped_column(Text, default="")
    reference_answer: Mapped[str] = mapped_column(Text, default="")
    expected_output: Mapped[str] = mapped_column(Text, default="")
    task_requirement: Mapped[str] = mapped_column(Text, default="")
    difficulty_level: Mapped[str] = mapped_column(String(20), default="")
    data_label: Mapped[str] = mapped_column(String(200), default="")
    extended_content: Mapped[str] = mapped_column(Text, default="{}")
    quality_flag: Mapped[str] = mapped_column(String(32), default="normal")
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DataTag(Base):
    __tablename__ = "data_tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80))
    tag_type: Mapped[str] = mapped_column(String(32), default="custom")
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="enabled")
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DatasetLog(Base):
    __tablename__ = "dataset_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operation_type: Mapped[str] = mapped_column(String(32))
    operation_desc: Mapped[str] = mapped_column(Text, default="")
    operator: Mapped[str] = mapped_column(String(80), default="")
    operation_result: Mapped[str] = mapped_column(String(20), default="success")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
