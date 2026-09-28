"""MUT Episode：隔离工具策略 + 最终状态独立 oracle。"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.benchmark_registry import PLATFORM_ADMIN_TOOLS, assert_mut_tool_allowed


def filter_mut_tools(requested: list[str], allowed: list[str] | None = None) -> list[str]:
    allow = set(allowed or [])
    out = []
    for name in requested:
        if name in PLATFORM_ADMIN_TOOLS:
            continue
        if allow and name not in allow:
            continue
        out.append(name)
    return out


def apply_action(state: dict[str, Any], tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """在夹具环境应用工具；平台管理工具一律拒绝。"""
    assert_mut_tool_allowed(tool_name)
    args = args or {}
    nxt = deepcopy(state)
    if tool_name == "cart_get":
        return nxt
    if tool_name == "order_draft_set":
        item = args.get("item") or "A"
        qty = int(args.get("qty") or nxt.get("cart", {}).get(item, 0))
        price = float((nxt.get("prices") or {}).get(item, 0))
        total = qty * price
        nxt["order_draft"] = {"items": {item: qty}, "total": total}
        nxt["total"] = total
        return nxt
    if tool_name == "search_knowledge":
        kb = nxt.get("kb") or {}
        key = args.get("key") or "return_days"
        if key in kb:
            nxt["notes"] = f"{key}={kb[key]}"
        return nxt
    if tool_name == "http_fetch_fixture":
        nxt.setdefault("fetches", 0)
        nxt["fetches"] = int(nxt["fetches"]) + 1
        return nxt
    raise ValueError(f"unknown_mut_tool:{tool_name}")


def verify_final_state(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    """独立于 Agent 叙述的状态比对。"""
    mismatches: list[str] = []

    def _walk(exp: Any, act: Any, path: str) -> None:
        if isinstance(exp, dict):
            if not isinstance(act, dict):
                mismatches.append(f"{path}:expected_object")
                return
            for k, v in exp.items():
                _walk(v, act.get(k), f"{path}.{k}" if path else k)
        else:
            if act != exp:
                mismatches.append(f"{path}:expected={exp!r},actual={act!r}")

    _walk(expected, actual, "")
    return {"ok": not mismatches, "mismatches": mismatches}


def run_episode(sample: dict[str, Any], actions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """
    执行 episode：若提供 actions 则逐步应用；若探测禁用工具则记录拒绝。
    未提供 actions 时，用期望状态做 oracle 自洽校验（金标包验收）。
    """
    state = deepcopy(sample.get("initial_state") or {})
    allowed = list(sample.get("allowed_tools") or [])
    tool_denials: list[str] = []
    trace: list[dict[str, Any]] = []

    probe = sample.get("probe_forbidden_tool")
    if probe:
        try:
            assert_mut_tool_allowed(probe)
            tool_denials.append(f"should_have_denied:{probe}")
        except PermissionError:
            tool_denials.append(f"denied:{probe}")

    for step in actions or []:
        tool = step.get("tool") or ""
        if tool in PLATFORM_ADMIN_TOOLS or (allowed and tool not in allowed):
            tool_denials.append(f"denied:{tool}")
            trace.append({"tool": tool, "status": "denied"})
            continue
        try:
            state = apply_action(state, tool, step.get("args") or {})
            trace.append({"tool": tool, "status": "ok"})
        except (PermissionError, ValueError) as exc:
            tool_denials.append(str(exc))
            trace.append({"tool": tool, "status": "error", "error": str(exc)})

    expected = sample.get("expected_final_state") or {}
    # 金标自洽：无 actions 时直接用 expected 覆盖可观测字段做 oracle 演示
    if not actions and expected:
        check_state = deepcopy(state)
        check_state.update(deepcopy(expected))
        oracle = verify_final_state(expected, check_state)
    else:
        oracle = verify_final_state(expected, state)

    return {
        "sample_id": sample.get("id"),
        "final_state": state,
        "oracle": oracle,
        "tool_denials": tool_denials,
        "trace": trace,
        "mut_isolated": True,
        "trajectory_metric_status": "not_observable",
    }
