from __future__ import annotations

import sqlite3
from pathlib import Path

from tools.cleanup_mock.fingerprint import file_sha256, resolve_sqlite_path


def _open_source(src: Path) -> sqlite3.Connection:
    uri = f"file:{src.as_posix()}?mode=ro"
    try:
        return sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError:
        return sqlite3.connect(str(src))


def consistent_backup(src: Path, dest: Path) -> dict:
    src = resolve_sqlite_path(str(src))
    dest = dest.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    src_conn = _open_source(src)
    try:
        try:
            src_conn.execute("PRAGMA wal_checkpoint(FULL)")
        except sqlite3.OperationalError:
            pass
        dst_conn = sqlite3.connect(dest)
        try:
            src_conn.backup(dst_conn)
            dst_conn.commit()
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    return {
        "path": str(dest),
        "source": str(src),
        "size": dest.stat().st_size,
        "sha256": file_sha256(dest),
    }
