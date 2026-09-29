"""在导入 app 之前设置独立 DATABASE_URL / uploads / logs，避免触碰业务库。"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

_ROOT = (Path(__file__).resolve().parent / "_isolated").resolve()
_ROOT.mkdir(exist_ok=True)
(_ROOT / "uploads").mkdir(exist_ok=True)
(_ROOT / "logs").mkdir(exist_ok=True)
(_ROOT / "backups").mkdir(exist_ok=True)


def assert_isolated_database(url: str) -> Path:
    if not url.startswith("sqlite+aiosqlite:///"):
        raise RuntimeError(
            f"Tests must use sqlite+aiosqlite under {_ROOT}; got non-sqlite URL: {url!r}"
        )
    parsed = urlparse(url)
    raw = unquote(parsed.path or "")
    # /E:/... — Windows absolute from sqlite+aiosqlite:///; else leading / is not a drive root.
    if raw.startswith("/") and len(raw) >= 3 and raw[1].isalpha() and raw[2] == ":":
        db_path = Path(raw[1:]).resolve()
    else:
        if raw.startswith("/"):
            raw = raw[1:]
        db_path = (Path.cwd() / raw).resolve()
    try:
        db_path.relative_to(_ROOT)
    except ValueError as exc:
        raise RuntimeError(
            f"Database path must be under {_ROOT}; got {db_path!s} from {url!r}"
        ) from exc
    return db_path


_default_db_url = "sqlite+aiosqlite:///" + (_ROOT / "wp00_test.db").as_posix()
_existing = os.environ.get("DATABASE_URL")
if _existing:
    try:
        assert_isolated_database(_existing)
        _database_url = _existing
    except RuntimeError:
        _database_url = _default_db_url
else:
    _database_url = _default_db_url

os.environ["DATABASE_URL"] = _database_url
assert_isolated_database(os.environ["DATABASE_URL"])

os.environ["UPLOAD_DIR"] = str(_ROOT / "uploads")
os.environ["LOG_DIR"] = str(_ROOT / "logs")
os.environ["BACKUP_DIR"] = str(_ROOT / "backups")
os.environ["LOG_LEVEL"] = "WARNING"
