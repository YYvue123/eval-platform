from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
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
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
