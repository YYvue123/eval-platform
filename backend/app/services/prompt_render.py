"""提示词变量填充。"""
from __future__ import annotations

import re


PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


class MissingRequiredVariable(ValueError):
    pass


def extract_variables(template: str) -> list[str]:
    return sorted(set(PLACEHOLDER.findall(template or "")))


def render_prompt(template: str, values: dict, *, variable_config: list | None = None, strict: bool = False) -> str:
    required_keys: set[str] = set()
    if variable_config:
        for row in variable_config:
            if isinstance(row, dict) and row.get("required"):
                k = row.get("key") or row.get("name")
                if k:
                    required_keys.add(str(k))
    check_keys = set(required_keys)
    if strict and not variable_config:
        check_keys |= set(extract_variables(template))
    missing = sorted(k for k in check_keys if values.get(k) in (None, ""))
    if missing:
        raise MissingRequiredVariable(f"缺少必填变量: {', '.join(missing)}")

    def repl(match):
        key = match.group(1)
        if key in values and values[key] is not None:
            return str(values[key])
        return match.group(0)

    return PLACEHOLDER.sub(repl, template or "")
