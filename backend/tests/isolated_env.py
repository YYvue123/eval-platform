"""在导入 app 之前设置独立 DATABASE_URL / uploads / logs，避免触碰业务库。"""
from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent / "_isolated"
_ROOT.mkdir(exist_ok=True)
(_ROOT / "uploads").mkdir(exist_ok=True)
(_ROOT / "logs").mkdir(exist_ok=True)
(_ROOT / "backups").mkdir(exist_ok=True)

os.environ.setdefault(
    "DATABASE_URL",
    "sqlite+aiosqlite:///" + (_ROOT / "wp00_test.db").as_posix(),
)
os.environ.setdefault("UPLOAD_DIR", str(_ROOT / "uploads"))
os.environ.setdefault("LOG_DIR", str(_ROOT / "logs"))
os.environ.setdefault("BACKUP_DIR", str(_ROOT / "backups"))
os.environ.setdefault("LOG_LEVEL", "WARNING")
