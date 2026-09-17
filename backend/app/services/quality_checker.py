"""数据集质量检测：可配置规则 + 默认规则库。"""
from __future__ import annotations

from collections import Counter
import hashlib

DEFAULT_RULE_DEFS = [
    {
        "code": "completeness_input",
        "name": "输入完整性",
        "category": "completeness",
        "severity": "error",
        "description": "输入内容不能为空",
        "config": {"field": "input_content"},
        "enabled": True,
    },
    {
        "code": "completeness_reference",
        "name": "参考答案完整性",
        "category": "completeness",
        "severity": "warning",
        "description": "参考答案为空时精确匹配打分不可用",
        "config": {"field": "reference_answer"},
        "enabled": True,
    },
    {
        "code": "format_length",
        "name": "长度上限",
        "category": "format",
        "severity": "warning",
        "description": "过长样本可能超出模型上下文",
        "config": {"field": "input_content", "max_length": 8000},
        "enabled": True,
    },
    {
        "code": "duplicate_exact",
        "name": "完全重复",
        "category": "duplicate",
        "severity": "warning",
        "description": "输入内容完全重复",
        "config": {},
        "enabled": True,
    },
    {
        "code": "anomaly_garbled",
        "name": "乱码异常",
        "category": "anomaly",
        "severity": "warning",
        "description": "替换符或控制字符比例过高",
        "config": {"ratio": 0.15},
        "enabled": True,
    },
]

DEFAULT_RULES = DEFAULT_RULE_DEFS


def _enabled_rules(rules: list[dict] | None) -> list[dict]:
    source = rules if rules else DEFAULT_RULE_DEFS
    return [r for r in source if r.get("enabled", True)]


def _garbled(text: str, ratio: float) -> bool:
    if not text:
        return False
    bad = sum(1 for ch in text if ch == "\ufffd" or (ord(ch) < 32 and ch not in "\t\n\r"))
    return bad / max(len(text), 1) >= ratio


def check_items(items: list[dict], rules: list[dict] | None = None) -> dict:
    total = len(items)
    active_rules = _enabled_rules(rules)
    codes = {r["code"] for r in active_rules}
    rule_map = {r["code"]: r for r in active_rules}

    missing_input = 0
    missing_ref = 0
    empty_both = 0
    too_long = 0
    garbled = 0
    hashes = []
    flags = []
    issue_records = []

    length_cfg = rule_map.get("format_length", {}).get("config") or {}
    max_len = int(length_cfg.get("max_length") or 8000)
    garbled_cfg = rule_map.get("anomaly_garbled", {}).get("config") or {}
    garbled_ratio = float(garbled_cfg.get("ratio") or 0.15)

    for idx, item in enumerate(items):
        inp = (item.get("input_content") or "").strip()
        ref = (item.get("reference_answer") or "").strip()
        flag = "normal"
        item_id = item.get("id")
        item_no = item.get("item_no") or (idx + 1)

        if "completeness_input" in codes or "completeness_reference" in codes:
            if not inp and not ref:
                empty_both += 1
                flag = "missing"
                if "completeness_input" in codes:
                    issue_records.append(_issue(item_id, item_no, rule_map["completeness_input"], "输入与参考答案均为空"))
            elif not inp and "completeness_input" in codes:
                missing_input += 1
                flag = "missing"
                issue_records.append(_issue(item_id, item_no, rule_map["completeness_input"], "输入内容为空"))
            elif not ref and "completeness_reference" in codes:
                missing_ref += 1
                flag = "missing_ref"
                issue_records.append(_issue(item_id, item_no, rule_map["completeness_reference"], "参考答案为空"))

        if "format_length" in codes and len(inp) > max_len:
            too_long += 1
            if flag == "normal":
                flag = "anomaly"
            issue_records.append(_issue(item_id, item_no, rule_map["format_length"], f"输入长度 {len(inp)} 超过 {max_len}"))

        if "anomaly_garbled" in codes and _garbled(inp, garbled_ratio):
            garbled += 1
            if flag == "normal":
                flag = "anomaly"
            issue_records.append(_issue(item_id, item_no, rule_map["anomaly_garbled"], "疑似乱码或控制字符过多"))

        digest = hashlib.sha256(inp.encode("utf-8")).hexdigest() if inp else ""
        hashes.append(digest)
        flags.append(flag)

    duplicate = 0
    if "duplicate_exact" in codes:
        counts = Counter(h for h in hashes if h)
        dup_keys = {h for h, n in counts.items() if n > 1}
        for i, digest in enumerate(hashes):
            if digest and digest in dup_keys:
                duplicate += 1
                if flags[i] == "normal":
                    flags[i] = "duplicate"
                item = items[i]
                issue_records.append(_issue(
                    item.get("id"),
                    item.get("item_no") or (i + 1),
                    rule_map["duplicate_exact"],
                    "与其他条目输入完全重复",
                ))

    issues = {
        "missing_input": missing_input,
        "missing_reference": missing_ref,
        "empty_rows": empty_both,
        "duplicates": duplicate,
        "too_long": too_long,
        "garbled": garbled,
    }
    penalty = (
        missing_input * 8
        + missing_ref * 4
        + empty_both * 12
        + duplicate * 3
        + too_long * 2
        + garbled * 3
    )
    score = 100.0 if total == 0 else max(0.0, round(100 - penalty / max(total, 1) * 10, 2))
    if total == 0:
        status = "check_failed"
    elif score >= 85:
        status = "passed"
    elif score >= 60:
        status = "needs_clean"
    else:
        status = "failed"

    suggestions = []
    if missing_input or empty_both:
        suggestions.append("补全缺失的输入内容后再发布。")
    if duplicate:
        suggestions.append("合并或删除重复样本，避免评测口径被放大。")
    if missing_ref:
        suggestions.append("参考答案缺失的条目只能做生成评测，不适合精确匹配打分。")
    if too_long:
        suggestions.append("过长样本可能超出模型上下文，建议拆分或截断。")
    if garbled:
        suggestions.append("检查编码，清理乱码与异常控制字符。")
    return {
        "total": total,
        "score": score,
        "status": status,
        "issues": issues,
        "suggestions": suggestions,
        "flags": flags,
        "issue_records": issue_records,
        "rules_applied": [r["code"] for r in active_rules],
    }


def _issue(item_id, item_no, rule: dict, description: str) -> dict:
    return {
        "item_id": item_id,
        "item_no": item_no,
        "rule_code": rule["code"],
        "issue_type": rule.get("category") or "",
        "severity": rule.get("severity") or "warning",
        "description": description,
    }
