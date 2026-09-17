import json
from datetime import datetime


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(text, default=None):
    if default is None:
        default = {}
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None
