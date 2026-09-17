"""内置评测工具：精确匹配 / 包含 / 正则 / 模糊匹配。"""
from __future__ import annotations

import re
from difflib import SequenceMatcher


def run_builtin_tool(resource_id: str, payload: dict) -> dict:
    prediction = str(payload.get("prediction") or payload.get("output") or "")
    reference = str(payload.get("reference") or payload.get("reference_answer") or "")
    pattern = str(payload.get("pattern") or "")
    if resource_id.endswith("exact_match"):
        passed = prediction.strip() == reference.strip()
        score = 1.0 if passed else 0.0
        return {"score": score, "passed": passed, "metrics": {"accuracy": score}}
    if resource_id.endswith("contains"):
        passed = bool(reference) and reference.strip() in prediction
        score = 1.0 if passed else 0.0
        return {"score": score, "passed": passed, "metrics": {"accuracy": score}}
    if resource_id.endswith("regex"):
        pat = pattern or reference
        try:
            passed = bool(pat) and re.search(pat, prediction, re.S) is not None
        except re.error:
            passed = False
        score = 1.0 if passed else 0.0
        return {"score": score, "passed": passed, "metrics": {"accuracy": score}}
    if resource_id.endswith("fuzzy"):
        score = SequenceMatcher(None, prediction.strip(), reference.strip()).ratio() if (prediction or reference) else 0.0
        passed = score >= float(payload.get("threshold") or 0.6)
        return {"score": round(score, 4), "passed": passed, "metrics": {"fuzzy": round(score, 4)}}
    raise ValueError(f"未知内置工具: {resource_id}")
