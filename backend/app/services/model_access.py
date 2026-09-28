"""模型访问配置冻结：按 version 写入不可变快照，执行时优先读取。"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import EvalModel, ModelAccessConfig, ModelVersion
from app.utils.jsonutil import dumps, loads

ACCESS_FIELD_NAMES = (
    "api_url",
    "request_method",
    "auth_type",
    "api_key",
    "served_model_name",
    "timeout",
    "retry_count",
    "channel_type",
    "request_template",
    "response_mapping",
    "parallel_limit",
)


def assert_channel_allowed(channel_type: str) -> None:
    ch = (channel_type or "https").lower()
    if settings.APP_ENV == "production" and ch == "plain":
        raise ValueError("生产环境禁止明文通道(channel_type=plain)")


def _auth_blob(m: EvalModel) -> str:
    return dumps({
        "auth_type": m.auth_type,
        "has_key": bool(m.api_key),
        "api_key": m.api_key or "",
        "served_model_name": m.served_model_name or "",
        "parallel_limit": int(m.parallel_limit or 4),
    })


async def get_access_for_version(db: AsyncSession, model_id: int, version_id: int | None) -> ModelAccessConfig | None:
    if not version_id:
        return None
    return await db.scalar(
        select(ModelAccessConfig).where(
            ModelAccessConfig.model_id == model_id,
            ModelAccessConfig.version_id == version_id,
        )
    )


async def insert_access_snapshot(db: AsyncSession, m: EvalModel) -> ModelAccessConfig:
    """为当前 current_version_id 写入新快照；若已存在则原样返回（不覆盖）。"""
    assert_channel_allowed(m.channel_type)
    existing = await get_access_for_version(db, m.id, m.current_version_id)
    if existing:
        return existing
    cfg = ModelAccessConfig(
        model_id=m.id,
        version_id=m.current_version_id,
        api_url=m.api_url or "",
        request_method=m.request_method or "POST",
        auth_type=m.auth_type or "bearer_token",
        auth_config=_auth_blob(m),
        request_template=m.request_template or "",
        response_mapping=m.response_mapping or "",
        timeout=int(m.timeout or 60),
        retry_count=int(m.retry_count or 1),
        channel_type=m.channel_type or "https",
    )
    db.add(cfg)
    await db.flush()
    return cfg


async def bump_version_and_freeze(db: AsyncSession, m: EvalModel, user_id: int | None, desc: str = "访问配置变更") -> ModelVersion:
    """访问配置变更时新建 ModelVersion + 不可变 AccessConfig。"""
    assert_channel_allowed(m.channel_type)
    base = (m.current_version or "V1.0").strip() or "V1.0"
    if base.upper().startswith("V") and "." in base:
        try:
            maj, minor = base[1:].split(".", 1)
            code = f"V{int(maj)}.{int(minor) + 1}"
        except ValueError:
            code = f"{base}-cfg"
    else:
        code = f"{base}-cfg"
    n = 0
    candidate = code
    while await db.scalar(select(ModelVersion.id).where(ModelVersion.model_id == m.id, ModelVersion.version_code == candidate)):
        n += 1
        candidate = f"{code}.{n}"
    ver = ModelVersion(model_id=m.id, version_code=candidate, version_desc=desc, creator_id=user_id)
    db.add(ver)
    await db.flush()
    m.current_version_id = ver.id
    m.current_version = ver.version_code
    await insert_access_snapshot(db, m)
    return ver


def model_call_view(model: EvalModel, cfg: ModelAccessConfig | None) -> Any:
    """构造 invoke/health 可用的模型视图；有快照时不读 live 可变字段。"""
    if cfg is None:
        return model
    auth = loads(cfg.auth_config or "{}", {}) or {}
    return SimpleNamespace(
        id=model.id,
        name=model.name,
        api_url=cfg.api_url or "",
        request_method=cfg.request_method or "POST",
        auth_type=cfg.auth_type or model.auth_type,
        api_key=auth.get("api_key") or auth.get("token") or "",
        served_model_name=auth.get("served_model_name") or model.served_model_name or model.name,
        timeout=int(cfg.timeout or 60),
        retry_count=int(cfg.retry_count or 1),
        channel_type=cfg.channel_type or "https",
        request_template=cfg.request_template or "",
        response_mapping=cfg.response_mapping or "",
        parallel_limit=int(auth.get("parallel_limit") or getattr(model, "parallel_limit", 4) or 4),
        consecutive_fail=getattr(model, "consecutive_fail", 0) or 0,
        circuit_open_until=getattr(model, "circuit_open_until", None),
        status=model.status,
        health_status=model.health_status,
        last_error=getattr(model, "last_error", "") or "",
    )
