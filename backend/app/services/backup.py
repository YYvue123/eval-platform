"""备份 SQLite 数据库文件。"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from app.config import settings


def backup_sqlite() -> dict:
    dest = Path(settings.BACKUP_DIR)
    dest.mkdir(parents=True, exist_ok=True)
    url = settings.DATABASE_URL
    src = Path("./eval_platform.db")
    if "sqlite" in url and "///" in url:
        raw = url.split("///", 1)[-1]
        src = Path(raw)
        if not src.is_absolute():
            src = Path(__file__).resolve().parent.parent.parent / src
    if not src.exists():
        raise FileNotFoundError(f"数据库文件不存在: {src}")
    name = f"eval-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.db"
    target = dest / name
    shutil.copy2(src, target)
    return {"path": str(target), "size": target.stat().st_size, "source": str(src)}
