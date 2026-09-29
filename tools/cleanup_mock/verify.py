from __future__ import annotations

import sqlite3
from pathlib import Path

from tools.cleanup_mock.fingerprint import resolve_sqlite_path


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _count_if(conn: sqlite3.Connection, present: set[str], table: str, column: str, sql: str, params=()) -> int:
    if table not in present:
        return 0
    if column not in _columns(conn, table):
        return 0
    return int(conn.execute(sql, params).fetchone()[0])


def verify_clean(db_path: Path) -> dict:
    path = resolve_sqlite_path(str(db_path))
    conn = sqlite3.connect(str(path))
    try:
        integrity_rows = conn.execute("PRAGMA integrity_check").fetchall()
        integrity = integrity_rows[0][0] if integrity_rows else "ok"
        foreign_key = [list(row) for row in conn.execute("PRAGMA foreign_key_check").fetchall()]
        present = _table_names(conn)
        simulation_results = _count_if(
            conn,
            present,
            "eval_results",
            "simulation",
            "SELECT COUNT(*) FROM eval_results WHERE simulation = 1",
        )
        simulation_tasks = _count_if(
            conn,
            present,
            "eval_tasks",
            "simulation",
            "SELECT COUNT(*) FROM eval_tasks WHERE simulation = 1",
        )
        mock_runs = _count_if(
            conn,
            present,
            "agent_runs",
            "provider",
            "SELECT COUNT(*) FROM agent_runs WHERE provider = ?",
            ("mock",),
        )
        ok = (
            integrity == "ok"
            and not foreign_key
            and simulation_results == 0
            and simulation_tasks == 0
            and mock_runs == 0
        )
        return {
            "ok": ok,
            "integrity": integrity,
            "foreign_key": foreign_key,
            "simulation_results": simulation_results,
            "simulation_tasks": simulation_tasks,
            "mock_runs": mock_runs,
        }
    finally:
        conn.close()
