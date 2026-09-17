"""提示词变量填充。"""
from __future__ import annotations

import re


PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def render_prompt(template: str, values: dict) -> str:
    def repl(match):
        key = match.group(1)
        if key in values and values[key] is not None:
            return str(values[key])
        return match.group(0)

    return PLACEHOLDER.sub(repl, template or "")


def extract_variables(template: str) -> list[str]:
    return sorted(set(PLACEHOLDER.findall(template or "")))
