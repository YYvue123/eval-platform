from __future__ import annotations

import ast
import hashlib
import json
import re
from typing import Any

_SECRET_KEYS = {
    "token",
    "api_key",
    "apikey",
    "authorization",
    "secret",
    "password",
    "credential",
}
_REDACTED = {"configured": True, "redacted": True}
_REDACTED_JSON = json.dumps(_REDACTED, separators=(",", ":"))
_STRINGIFIED_SECRET = re.compile(
    r"""(?ix)
    (?P<prefix>
        (?P<quote>["']?)
        (?:token|api_key|apikey|authorization|secret|password|credential)
        (?P=quote)\s*[:=]\s*
    )
    (?P<value>
        "(?:\\.|[^"\\])*"
        |'(?:\\.|[^'\\])*'
        |[^;,&\s{}\]\r\n]+
    )
    """
)


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                dict(_REDACTED)
                if str(key).lower() in _SECRET_KEYS and item
                else redact_secrets(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def _structured_error_text(value: str) -> str | None:
    candidates = [value]
    if r"\"" in value or r"\'" in value:
        candidates.append(value.replace(r"\"", '"').replace(r"\'", "'"))
    for candidate in candidates:
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(candidate)
            except (ValueError, SyntaxError, json.JSONDecodeError):
                continue
            if isinstance(parsed, (dict, list)):
                return json.dumps(
                    redact_secrets(parsed),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
    return None


def redact_error_text(value: str) -> str:
    structured = _structured_error_text(value)
    if structured is not None:
        return structured
    normalized = value.replace(r"\"", '"').replace(r"\'", "'")
    return _STRINGIFIED_SECRET.sub(
        lambda match: f"{match.group('prefix')}{_REDACTED_JSON}",
        normalized,
    )


def sanitize_error_text(value: str) -> str:
    return redact_error_text(value)


def safe_error_message(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(
            redact_secrets(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return redact_error_text(str(value))


def evidence_digest(value: Any, limit: int = 4000) -> tuple[str, str]:
    serialized = json.dumps(
        redact_secrets(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return serialized[:limit], hashlib.sha256(serialized.encode("utf-8")).hexdigest()
