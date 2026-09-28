"""副作用策略与出口 allowlist（非容器沙箱）。"""
from __future__ import annotations

from urllib.parse import urlparse


def has_side_effects(manifest: dict) -> bool:
    top = manifest.get("side_effects")
    if isinstance(top, list) and top:
        return True
    if isinstance(top, str) and top not in {"", "none"}:
        return True
    caps = manifest.get("capabilities") or {}
    se = caps.get("side_effects")
    if se and se not in {"none", False, [], ""}:
        return True
    return False


def mock_strategy(manifest: dict) -> str:
    """dry_run | stub | record | deny。默认 stub。"""
    for item in manifest.get("side_effects") or []:
        if isinstance(item, dict) and item.get("mock_strategy"):
            return str(item["mock_strategy"])
    caps = manifest.get("capabilities") or {}
    if caps.get("mock_strategy"):
        return str(caps["mock_strategy"])
    return "stub"


def stub_side_effect_result(manifest: dict) -> dict:
    strategy = mock_strategy(manifest)
    if strategy == "deny":
        raise PermissionError("资源声明副作用且策略为 deny，拒绝执行")
    return {
        "stubbed": True,
        "mocked": True,
        "mock_strategy": strategy,
        "message": f"副作用已按 {strategy} 策略短路，未执行真实副作用",
        "score": 0.0,
        "passed": False,
        "side_effects": manifest.get("side_effects") or [],
    }


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
