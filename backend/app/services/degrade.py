"""进程内可控降级标志（故障注入 / 发布探针）。"""
from __future__ import annotations

from threading import Lock
from typing import Any

_lock = Lock()
_state: dict[str, Any] = {
    "db_unavailable": False,
    "cert_expired": False,
    "reason": "",
}


def get_degrade() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def set_degrade(*, db_unavailable: bool | None = None, cert_expired: bool | None = None, reason: str = "") -> dict[str, Any]:
    with _lock:
        if db_unavailable is not None:
            _state["db_unavailable"] = bool(db_unavailable)
        if cert_expired is not None:
            _state["cert_expired"] = bool(cert_expired)
        if reason is not None:
            _state["reason"] = reason or ""
        return dict(_state)


def clear_degrade() -> dict[str, Any]:
    with _lock:
        _state["db_unavailable"] = False
        _state["cert_expired"] = False
        _state["reason"] = ""
        return dict(_state)


def is_ready() -> tuple[bool, str]:
    with _lock:
        if _state["db_unavailable"]:
            return False, "degrade:db_unavailable"
        if _state["cert_expired"]:
            return False, "degrade:cert_expired"
    return True, "ok"
