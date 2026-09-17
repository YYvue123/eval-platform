"""数据集质量检测：完整性、格式、重复、异常。"""
from __future__ import annotations

from collections import Counter
import hashlib


def check_items(items: list[dict]) -> dict:
    total = len(items)
    missing_input = 0
    missing_ref = 0
    empty_both = 0
    too_long = 0
    hashes = []
    flags = []
    for item in items:
        inp = (item.get("input_content") or "").strip()
        ref = (item.get("reference_answer") or "").strip()
        flag = "normal"
        if not inp and not ref:
            empty_both += 1
            flag = "missing"
        elif not inp:
            missing_input += 1
            flag = "missing"
        elif not ref:
            missing_ref += 1
            flag = "missing_ref"
        if len(inp) > 8000:
            too_long += 1
            if flag == "normal":
                flag = "anomaly"
        digest = hashlib.sha256(inp.encode("utf-8")).hexdigest() if inp else ""
        hashes.append(digest)
        flags.append(flag)

    counts = Counter(h for h in hashes if h)
    dup_keys = {h for h, n in counts.items() if n > 1}
    duplicate = 0
    for i, digest in enumerate(hashes):
        if digest and digest in dup_keys:
            duplicate += 1
            if flags[i] == "normal":
                flags[i] = "duplicate"

    issues = {
        "missing_input": missing_input,
        "missing_reference": missing_ref,
        "empty_rows": empty_both,
        "duplicates": duplicate,
        "too_long": too_long,
    }
    penalty = (
        missing_input * 8
        + missing_ref * 4
        + empty_both * 12
        + duplicate * 3
        + too_long * 2
    )
    score = 100.0 if total == 0 else max(0.0, round(100 - penalty / max(total, 1) * 10, 2))
    if total == 0:
        status = "failed"
    elif score >= 85:
        status = "passed"
    elif score >= 60:
        status = "warning"
    else:
        status = "failed"
    suggestions = []
    if missing_input:
        suggestions.append("补全缺失的输入内容后再发布。")
    if duplicate:
        suggestions.append("合并或删除重复样本，避免评测口径被放大。")
    if missing_ref:
        suggestions.append("参考答案缺失的条目只能做生成评测，不适合精确匹配打分。")
    if too_long:
        suggestions.append("过长样本可能超出模型上下文，建议拆分或截断。")
    return {
        "total": total,
        "score": score,
        "status": status,
        "issues": issues,
        "suggestions": suggestions,
        "flags": flags,
    }
