"""副作用策略与出口 allowlist（非容器沙箱）。"""
from __future__ import annotations

from urllib.parse import urlparse


class SideEffectBlocked(PermissionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _declared(value) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "none"}
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return bool(value)


def has_side_effects(manifest: dict) -> bool:
    if not isinstance(manifest, dict):
        return False
    if _declared(manifest.get("side_effects")):
        return True
    caps = manifest.get("capabilities") or {}
    if isinstance(caps, dict) and _declared(caps.get("side_effects")):
        return True
    return False


def mock_strategy(manifest: dict) -> str:
    """dry_run | stub | record | deny。未声明时不使用。"""
    raw = manifest.get("side_effects") if isinstance(manifest, dict) else None
    items = raw if isinstance(raw, list) else []
    for item in items:
        if isinstance(item, dict) and item.get("mock_strategy"):
            return str(item["mock_strategy"])
    caps = (manifest.get("capabilities") or {}) if isinstance(manifest, dict) else {}
    if isinstance(caps, dict) and caps.get("mock_strategy"):
        return str(caps["mock_strategy"])
    return "stub"


def side_effect_block(manifest: dict) -> SideEffectBlocked:
    """声明了副作用但没有受控真实执行时，一律阻断，不返回 stub 成功。"""
    strategy = mock_strategy(manifest)
    if strategy == "deny":
        return SideEffectBlocked("SIDE_EFFECT_DENIED", "资源声明副作用且策略为 deny，拒绝执行")
    return SideEffectBlocked(
        "SIDE_EFFECT_BLOCKED",
        f"副作用策略 {strategy} 未接入受控真实执行，拒绝记为成功",
    )


def stub_side_effect_result(manifest: dict) -> dict:
    raise side_effect_block(manifest)


def egress_allowlist(manifest: dict) -> list[str]:
    interfaces = manifest.get("interfaces") or {}
    caps = manifest.get("capabilities") or {}
    raw = interfaces.get("egress_allowlist") or caps.get("egress_allowlist") or []
    if isinstance(raw, str):
        return [x.strip() for x in raw.split(",") if x.strip()]
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return []


def assert_egress_allowed(url: str, manifest: dict | None = None, allowlist: list[str] | None = None) -> None:
    hosts = allowlist if allowlist is not None else egress_allowlist(manifest or {})
    if not hosts:
        return
    host = (urlparse(url).hostname or "").lower()
    if not host:
        raise ValueError("无法解析出口 host")
    allowed = {h.lower() for h in hosts}
    if host not in allowed and not any(host.endswith("." + h) for h in allowed):
        raise PermissionError(f"出口 host 不在 allowlist: {host}")
