from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlparse


def resolve_sqlite_path(url_or_path: str) -> Path:
    raw = url_or_path.strip()
    if "sqlite" in raw and "///" in raw:
        parsed = urlparse(raw)
        raw = unquote(parsed.path or "")
        if raw.startswith("/") and len(raw) >= 3 and raw[1].isalpha() and raw[2] == ":":
            raw = raw[1:]
        elif raw.startswith("/"):
            raw = raw[1:]
    path = Path(raw)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    return path


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def target_fingerprint(path: Path) -> str:
    resolved = path.resolve()
    inner = file_sha256(resolved) + "|" + str(resolved)
    return "sha256:" + hashlib.sha256(inner.encode("utf-8")).hexdigest()


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def manifest_hash(obj: dict) -> str:
    copy = {k: v for k, v in obj.items() if k != "manifest_hash"}
    return hashlib.sha256(canonical_json(copy).encode("utf-8")).hexdigest()
