"""备份 SQLite 数据库文件与恢复演练。"""
from __future__ import annotations

import hashlib
import shutil
import time
from datetime import datetime
from pathlib import Path

from app.config import settings


def _db_path() -> Path:
    url = settings.DATABASE_URL
    src = Path("./eval_platform.db")
    if "sqlite" in url and "///" in url:
        raw = url.split("///", 1)[-1]
        src = Path(raw)
        if not src.is_absolute():
            src = Path(__file__).resolve().parent.parent.parent / src
    return src


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def backup_sqlite() -> dict:
    dest = Path(settings.BACKUP_DIR)
    dest.mkdir(parents=True, exist_ok=True)
    src = _db_path()
    if not src.exists():
        raise FileNotFoundError(f"数据库文件不存在: {src}")
    name = f"eval-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.db"
    target = dest / name
    shutil.copy2(src, target)
    return {
        "path": str(target),
        "size": target.stat().st_size,
        "source": str(src),
        "sha256": _sha256(target),
    }


def restore_drill(*, backup_path: str | None = None) -> dict:
    """
    隔离恢复演练：拷贝备份到 backups/restore-drill/，校验 hash，测量 RTO；
    RPO 以源库 mtime 与备份文件 mtime 差近似（秒）。
    不覆盖生产库文件。
    """
    t0 = time.perf_counter()
    dest_root = Path(settings.BACKUP_DIR)
    dest_root.mkdir(parents=True, exist_ok=True)
    src = _db_path()
    if not src.exists():
        raise FileNotFoundError(f"数据库文件不存在: {src}")

    if backup_path:
        backup = Path(backup_path)
        if not backup.exists():
            raise FileNotFoundError(f"备份不存在: {backup}")
    else:
        # 先打一份新鲜备份再演练
        snap = backup_sqlite()
        backup = Path(snap["path"])

    restore_dir = dest_root / "restore-drill"
    restore_dir.mkdir(parents=True, exist_ok=True)
    target = restore_dir / f"restored-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.db"
    shutil.copy2(backup, target)

    src_hash = _sha256(backup)
    dst_hash = _sha256(target)
    hash_ok = src_hash == dst_hash

    rto_seconds = round(time.perf_counter() - t0, 3)
    # RPO：源库相对备份的时间差（备份越新 RPO 越小）
    rpo_seconds = max(0.0, round(src.stat().st_mtime - backup.stat().st_mtime, 3))
    if rpo_seconds < 0:
        rpo_seconds = 0.0

    return {
        "ok": hash_ok,
        "backup_path": str(backup),
        "restored_path": str(target),
        "sha256": dst_hash,
        "hash_match": hash_ok,
        "rpo_seconds": rpo_seconds,
        "rto_seconds": rto_seconds,
        "size": target.stat().st_size,
        "note": "隔离目录恢复，未覆盖活动库；RPO 以 mtime 差近似",
    }
