"""生产环境启动与引导凭证门禁。"""
from __future__ import annotations

import os

from app.config import settings

DEFAULT_SECRET_KEY = "eval-platform-secret-key-change-in-production"
DEFAULT_ADMIN_PASSWORD = "admin123"


def is_production() -> bool:
    return (settings.APP_ENV or "").strip().lower() == "production"


def assert_production_safe() -> None:
    """生产启动前校验：禁止默认 SECRET_KEY。"""
    if not is_production():
        return
    secret = (settings.SECRET_KEY or "").strip()
    if not secret or secret == DEFAULT_SECRET_KEY or len(secret) < 24:
        raise RuntimeError(
            "production requires a strong non-default SECRET_KEY "
            "(>=24 chars, not the sample value in config/.env.example)"
        )


def bootstrap_admin_password() -> str | None:
    """
    返回允许用于首次引导 admin 的密码。
    生产：必须显式设置 ADMIN_BOOTSTRAP_PASSWORD，且不得为默认 admin123。
    非生产：允许默认 admin123（开发/测试）。
    """
    explicit = (os.environ.get("ADMIN_BOOTSTRAP_PASSWORD") or "").strip()
    if is_production():
        if not explicit:
            return None
        if explicit == DEFAULT_ADMIN_PASSWORD:
            raise RuntimeError(
                "production ADMIN_BOOTSTRAP_PASSWORD must not be the default admin123"
            )
        return explicit
    return explicit or DEFAULT_ADMIN_PASSWORD
