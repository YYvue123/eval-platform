from __future__ import annotations

import argparse
import json
import sys
from contextlib import nullcontext
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_BACKEND = _REPO / "backend"
for _p in (_REPO, _BACKEND):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)

from tools.cleanup_mock.fingerprint import resolve_sqlite_path, target_fingerprint
from tools.real_fill.client import FillClient
from tools.real_fill.scenarios import (
    real01_accounts,
    real02_dataset,
    real03_models,
    real04_tools,
    real05_mcp,
    real06_agent,
    real07_formal_task,
    real08_prompts,
    real09_safety,
    real10_leaderboard,
    real11_shadow,
    real12_ops,
)

SCENARIOS = [
    "REAL01",
    "REAL02",
    "REAL03",
    "REAL04",
    "REAL05",
    "REAL06",
    "REAL07",
    "REAL08",
    "REAL09",
    "REAL10",
    "REAL11",
    "REAL12",
]


def _normalize_fingerprint(value: str) -> str:
    raw = (value or "").strip()
    if raw.startswith("sha256:"):
        return raw
    if len(raw) == 64 and all(c in "0123456789abcdefABCDEF" for c in raw):
        return "sha256:" + raw.lower()
    return raw


def _fingerprint_matches(db: Path, confirm: str | None) -> bool:
    if not confirm:
        return False
    return _normalize_fingerprint(confirm) == target_fingerprint(db)


def _guard_row(scenario: str, fn):
    try:
        row = fn()
        if not isinstance(row, dict):
            return {"scenario": scenario, "result": "fail", "blocking_reason": "invalid_row"}
        row.setdefault("scenario", scenario)
        return row
    except Exception as exc:
        return {
            "scenario": scenario,
            "result": "fail",
            "blocking_reason": type(exc).__name__,
        }


def dump_isolated_evidence(admin: FillClient, viewer: FillClient) -> list[dict]:
    from tests.followup_helpers import stats_service

    rows: list[dict] = []
    r01 = _guard_row("REAL01", lambda: real01_accounts(admin, viewer))
    rows.append(r01)
    r02 = _guard_row("REAL02", lambda: real02_dataset(admin))
    rows.append(r02)
    r03 = _guard_row("REAL03", lambda: real03_models(admin))
    rows.append(r03)

    with stats_service() as stats_url:
        r04 = _guard_row("REAL04", lambda: real04_tools(admin, stats_url))
        rows.append(r04)
        r05 = _guard_row("REAL05", lambda: real05_mcp(admin, stats_url))
        rows.append(r05)

    parse_id = r04.get("parse_resource_id") if r04.get("result") == "pass" else None
    rows.append(
        _guard_row(
            "REAL06",
            lambda: real06_agent(admin, parse_resource_id=parse_id),
        )
    )
    rows.append(
        _guard_row(
            "REAL07",
            lambda: real07_formal_task(
                admin,
                dataset_id=r02.get("dataset_id"),
                version_id=r02.get("version_id"),
                model_id=r03.get("model_id") or 0,
            ),
        )
    )
    rows.append(
        _guard_row(
            "REAL08",
            lambda: real08_prompts(admin, dataset_id=r02.get("dataset_id")),
        )
    )
    rows.append(_guard_row("REAL09", lambda: real09_safety(admin)))
    rows.append(_guard_row("REAL10", lambda: real10_leaderboard(admin)))
    rows.append(_guard_row("REAL11", lambda: real11_shadow(admin)))
    rows.append(_guard_row("REAL12", lambda: real12_ops(admin)))
    return rows


def _run_selected(raw, selected: list[str]) -> list[dict]:
    from tests.followup_helpers import stats_service

    admin = FillClient(raw)
    viewer = FillClient(raw)
    need_stats = any(sid in {"REAL04", "REAL05"} for sid in selected)
    ctx: dict = {}
    rows: list[dict] = []
    stats_cm = stats_service() if need_stats else nullcontext(None)
    with stats_cm as stats_url:
        for sid in selected:
            if sid not in SCENARIOS:
                rows.append(
                    {
                        "scenario": sid,
                        "result": "fail",
                        "blocking_reason": "unknown_scenario",
                    }
                )
                continue
            if sid == "REAL01":
                rows.append(_guard_row(sid, lambda: real01_accounts(admin, viewer)))
            elif sid == "REAL02":
                row = _guard_row(sid, lambda: real02_dataset(admin))
                ctx["dataset_id"] = row.get("dataset_id")
                ctx["version_id"] = row.get("version_id")
                rows.append(row)
            elif sid == "REAL03":
                row = _guard_row(sid, lambda: real03_models(admin))
                ctx["model_id"] = row.get("model_id")
                rows.append(row)
            elif sid == "REAL04":
                row = _guard_row(sid, lambda: real04_tools(admin, stats_url))
                ctx["parse_resource_id"] = row.get("parse_resource_id")
                rows.append(row)
            elif sid == "REAL05":
                rows.append(_guard_row(sid, lambda: real05_mcp(admin, stats_url)))
            elif sid == "REAL06":
                rows.append(
                    _guard_row(
                        sid,
                        lambda: real06_agent(
                            admin,
                            parse_resource_id=ctx.get("parse_resource_id"),
                        ),
                    )
                )
            elif sid == "REAL07":
                rows.append(
                    _guard_row(
                        sid,
                        lambda: real07_formal_task(
                            admin,
                            dataset_id=ctx.get("dataset_id"),
                            version_id=ctx.get("version_id"),
                            model_id=ctx.get("model_id") or 0,
                        ),
                    )
                )
            elif sid == "REAL08":
                rows.append(
                    _guard_row(
                        sid,
                        lambda: real08_prompts(admin, dataset_id=ctx.get("dataset_id")),
                    )
                )
            elif sid == "REAL09":
                rows.append(_guard_row(sid, lambda: real09_safety(admin)))
            elif sid == "REAL10":
                rows.append(_guard_row(sid, lambda: real10_leaderboard(admin)))
            elif sid == "REAL11":
                rows.append(_guard_row(sid, lambda: real11_shadow(admin)))
            elif sid == "REAL12":
                rows.append(_guard_row(sid, lambda: real12_ops(admin)))
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tools.real_fill")
    parser.add_argument("--base-url")
    parser.add_argument("--db", required=True)
    parser.add_argument("--confirm-fingerprint")
    parser.add_argument("--only", default="")
    args = parser.parse_args(argv)

    db = resolve_sqlite_path(args.db)
    if not db.is_file():
        print("fingerprint missing or mismatch", file=sys.stderr)
        return 1
    if not _fingerprint_matches(db, args.confirm_fingerprint):
        print("fingerprint missing or mismatch", file=sys.stderr)
        return 1

    selected = [part.strip().upper() for part in (args.only or "").split(",") if part.strip()]
    if not selected:
        print("dry-run scenarios (no remote writes):")
        for sid in SCENARIOS:
            print(sid)
        if args.base_url:
            try:
                import httpx

                httpx.get(args.base_url.rstrip("/") + "/api/live", timeout=2.0)
            except Exception:
                pass
        return 0

    if not args.base_url:
        print("--base-url required when running scenarios", file=sys.stderr)
        return 1

    import httpx

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=90.0) as raw:
        rows = _run_selected(raw, selected)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
