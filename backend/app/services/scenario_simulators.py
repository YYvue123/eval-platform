"""场景轻量模拟器：代码禁宿主执行、表格计算、媒体探测、MUT 环境。"""
from __future__ import annotations

import ast
import operator
from copy import deepcopy
from typing import Any

from app.services import media_adapter, mut_oracle
from app.services.benchmark_packs import load_pack

SIMULATOR_CODES = {
    "sim.code_sandbox": "代码隔离裁决（禁宿主 exec）",
    "sim.table_calc": "表格只读计算",
    "sim.media_probe": "媒体 fixture 可解析探测",
    "sim.mut_episode": "被测 Agent Episode 环境",
}


class HostExecutionForbidden(RuntimeError):
    pass


def _normalize_code(src: str) -> str:
    return "\n".join(line.rstrip() for line in (src or "").strip().splitlines())


def code_sandbox_score(sample: dict[str, Any], candidate: str | None = None) -> dict[str, Any]:
    """禁止用参考解冒充候选；无隔离执行器时不得记 tests passed。"""
    if sample.get("execute_on_host"):
        raise HostExecutionForbidden("code_must_not_execute_on_host")
    if candidate is None or str(candidate).strip() == "":
        return {
            "simulator": "sim.code_sandbox",
            "host_executed": False,
            "syntax_ok": None,
            "matches_reference": None,
            "tests_total": len(sample.get("tests") or []),
            "tests_passed": None,
            "code_pass": None,
            "status": "not_run",
            "reason": "candidate_required",
        }
    ref = _normalize_code(sample.get("reference") or "")
    cand = _normalize_code(candidate)
    syntax_ok = True
    try:
        ast.parse(cand)
    except SyntaxError:
        syntax_ok = False
    # 无隔离执行器：不得将文本匹配参考解记为正式通过
    return {
        "simulator": "sim.code_sandbox",
        "host_executed": False,
        "syntax_ok": syntax_ok,
        "matches_reference": bool(ref) and cand == ref,
        "tests_total": len(sample.get("tests") or []),
        "tests_passed": None,
        "code_pass": None,
        "status": "not_run",
        "reason": "isolated_executor_unavailable",
    }


_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def table_calc(sample: dict[str, Any]) -> dict[str, Any]:
    table = sample.get("table") or {}
    cols = table.get("columns") or []
    rows = table.get("rows") or []
    question = (sample.get("question") or "").lower()
    result: Any = None
    if "利润" in question or "profit" in question:
        if "营收" in cols and "成本" in cols:
            i_r, i_c = cols.index("营收"), cols.index("成本")
            result = sum(float(r[i_r]) - float(r[i_c]) for r in rows)
    elif "销售" in question or "总销售" in question:
        if "销量" in cols and "单价" in cols:
            i_q, i_p = cols.index("销量"), cols.index("单价")
            result = sum(float(r[i_q]) * float(r[i_p]) for r in rows)
    elif "超支" in question:
        if "预算" in cols and "实际" in cols and "部门" in cols:
            i_d, i_b, i_a = cols.index("部门"), cols.index("预算"), cols.index("实际")
            over = [(r[i_d], float(r[i_a]) - float(r[i_b])) for r in rows if float(r[i_a]) > float(r[i_b])]
            if over:
                name, amt = over[0]
                result = f"{name}超支{int(amt) if amt == int(amt) else amt}"
    ref = str(sample.get("reference") or "")
    ok = str(result) == ref or (result is not None and abs(float(result) - float(ref)) <= float(sample.get("tolerance") or 0))
    return {
        "simulator": "sim.table_calc",
        "result": result,
        "reference": ref,
        "ok": ok,
        "status": "ok" if ok else "fail",
    }


def media_probe(sample: dict[str, Any]) -> dict[str, Any]:
    errors = media_adapter.validate_media_sample(sample)
    info = None
    if not errors:
        info = media_adapter.describe_media(sample["media_uri"], sample["media_type"])
    ok = not errors and bool(info and info.get("decodable"))
    return {
        "simulator": "sim.media_probe",
        "ok": ok,
        "errors": errors,
        "media": info,
        "status": "ok" if ok else ("fail" if errors else "not_run"),
    }


def mut_episode_sim(sample: dict[str, Any], actions: list[dict] | None = None) -> dict[str, Any]:
    result = mut_oracle.run_episode(sample, actions)
    return {
        "simulator": "sim.mut_episode",
        "ok": bool(result["oracle"]["ok"]),
        **result,
        "status": "ok" if result["oracle"]["ok"] else "fail",
    }


def list_simulators() -> list[dict[str, str]]:
    return [{"code": k, "name": v} for k, v in SIMULATOR_CODES.items()]


def run_simulator(sim_code: str, suite_code: str, sample_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
    pack = load_pack(suite_code)
    samples = pack.get("samples") or []
    sample = None
    if sample_id:
        sample = next((s for s in samples if s.get("id") == sample_id), None)
    else:
        sample = samples[0] if samples else None
    if not sample:
        raise ValueError("sample_not_found")
    sample = deepcopy(sample)
    if sim_code == "sim.code_sandbox":
        return code_sandbox_score(sample, kwargs.get("candidate"))
    if sim_code == "sim.table_calc":
        return table_calc(sample)
    if sim_code == "sim.media_probe":
        return media_probe(sample)
    if sim_code == "sim.mut_episode":
        return mut_episode_sim(sample, kwargs.get("actions"))
    raise ValueError(f"unknown_simulator:{sim_code}")
