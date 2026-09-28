"""基准场景包加载：金标样本、校准报告、套件资源门禁。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "benchmarks"

PACK_INDEX: dict[str, dict[str, str]] = {
    "bench.chat": {"path": "text/chat.json", "calibration": "calibration/text-5scenes.md"},
    "bench.table": {"path": "text/table.json", "calibration": "calibration/text-5scenes.md"},
    "bench.writing": {"path": "text/writing.json", "calibration": "calibration/text-5scenes.md"},
    "bench.rag": {"path": "text/rag.json", "calibration": "calibration/text-5scenes.md"},
    "bench.code": {"path": "text/code.json", "calibration": "calibration/text-5scenes.md"},
    "bench.finance": {"path": "industry/finance.json", "calibration": "calibration/media-mut-industry.md"},
    "bench.gov": {"path": "industry/gov.json", "calibration": "calibration/media-mut-industry.md"},
    "bench.media.video": {"path": "media/manifest.json", "calibration": "calibration/media-mut-industry.md"},
    "bench.mut.episode": {"path": "mut/episode.json", "calibration": "calibration/media-mut-industry.md"},
}


def fixtures_root() -> Path:
    return FIXTURES_ROOT


def pack_path(suite_code: str) -> Path | None:
    meta = PACK_INDEX.get(suite_code)
    if not meta:
        return None
    return FIXTURES_ROOT / meta["path"]


def calibration_path(suite_code: str) -> Path | None:
    meta = PACK_INDEX.get(suite_code)
    if not meta:
        return None
    return FIXTURES_ROOT / meta["calibration"]


@lru_cache(maxsize=32)
def load_pack(suite_code: str) -> dict[str, Any]:
    p = pack_path(suite_code)
    if not p or not p.is_file():
        raise FileNotFoundError(f"benchmark_pack_missing:{suite_code}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data.get("samples"), list) or not data["samples"]:
        raise ValueError(f"benchmark_pack_empty:{suite_code}")
    return data


def load_calibration_text(suite_code: str) -> str:
    p = calibration_path(suite_code)
    if not p or not p.is_file():
        return ""
    return p.read_text(encoding="utf-8").strip()


def pack_summary(suite_code: str) -> dict[str, Any]:
    pack = load_pack(suite_code)
    cal = load_calibration_text(suite_code)
    return {
        "suite_code": suite_code,
        "version": pack.get("version"),
        "license": pack.get("license"),
        "oracle_type": pack.get("oracle_type"),
        "sample_count": len(pack.get("samples") or []),
        "samples": pack.get("samples") or [],
        "calibration_report": cal[:500],
        "calibration_ok": bool(cal) and "accepted" in cal.lower(),
        "pack_path": str(pack_path(suite_code)),
    }


def assert_pack_ready_resources(suite_code: str) -> list[str]:
    """返回 blockers；空列表表示资源齐备。"""
    blockers: list[str] = []
    try:
        pack = load_pack(suite_code)
    except (FileNotFoundError, ValueError) as exc:
        return [str(exc)]
    if not pack.get("samples"):
        blockers.append("missing_real_inputs")
    cal = load_calibration_text(suite_code)
    if not cal:
        blockers.append("calibration_missing")
    elif "accepted" not in cal.lower():
        blockers.append("calibration_not_accepted")
    license_ = (pack.get("license") or "").strip()
    if not license_ or license_ == "tbd":
        blockers.append("license_unset")
    # 媒体包额外检查
    if suite_code.startswith("bench.media"):
        for s in pack["samples"]:
            if s.get("media_as_string") or (isinstance(s.get("media"), str) and not s.get("media_uri")):
                blockers.append("media_string_description_forbidden")
                break
            if not s.get("media_uri"):
                blockers.append("media_uri_required")
                break
    if suite_code == "bench.code" and pack.get("host_exec_forbidden") is False:
        blockers.append("code_host_exec_forbidden")
    return blockers


def list_available_packs() -> list[dict[str, Any]]:
    out = []
    for code in PACK_INDEX:
        try:
            out.append(pack_summary(code))
        except (FileNotFoundError, ValueError) as exc:
            out.append({"suite_code": code, "error": str(exc), "sample_count": 0})
    return out
