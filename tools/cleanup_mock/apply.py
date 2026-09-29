from __future__ import annotations

import sqlite3
from pathlib import Path

from tools.cleanup_mock.backup_sqlite import consistent_backup
from tools.cleanup_mock.fingerprint import manifest_hash, resolve_sqlite_path, target_fingerprint
from tools.cleanup_mock.inventory import KNOWN_TABLES

BUSY_STATUSES = ("running", "queued", "leased", "cancelling")

DELETE_ORDER = (
    "agent_events",
    "agent_messages",
    "eval_results",
    "eval_lineages",
    "task_events",
    "task_subtasks",
    "report_jobs",
    "eval_tasks",
    "agent_runs",
)


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def apply_plan(db_path, plan, *, confirm_fingerprint: str, backup_dir: Path) -> dict:
    if not confirm_fingerprint:
        raise ValueError("confirm_fingerprint is required")

    path = resolve_sqlite_path(str(db_path))
    current_fp = target_fingerprint(path)
    plan_fp = (plan.get("target") or {}).get("fingerprint")
    if confirm_fingerprint != current_fp or plan_fp != current_fp:
        raise ValueError("fingerprint mismatch")

    expected_hash = manifest_hash(plan)
    if plan.get("manifest_hash") != expected_hash:
        raise ValueError("manifest_hash mismatch")

    conn = sqlite3.connect(str(path))
    try:
        present = _table_names(conn)
        if "eval_tasks" in present:
            cols = _columns(conn, "eval_tasks")
            if "status" in cols:
                placeholders = ",".join("?" * len(BUSY_STATUSES))
                busy = conn.execute(
                    f"SELECT COUNT(*) FROM eval_tasks WHERE status IN ({placeholders})",
                    BUSY_STATUSES,
                ).fetchone()[0]
                if busy:
                    raise ValueError(
                        "eval_tasks.status in running/queued/leased/cancelling"
                    )

        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        dest = backup_dir / f"{path.stem}.pre-apply.db"
        backup_info = consistent_backup(path, dest)

        by_table: dict[str, list[int]] = {}
        for action in plan.get("actions") or []:
            table = action["table"]
            if table not in KNOWN_TABLES:
                raise ValueError(f"unknown table in plan: {table}")
            by_table.setdefault(table, []).append(int(action["pk"]))

        try:
            conn.execute("BEGIN")
            for table in DELETE_ORDER:
                pks = by_table.get(table)
                if not pks:
                    continue
                if table not in present:
                    continue
                placeholders = ",".join("?" * len(pks))
                conn.execute(f"DELETE FROM {table} WHERE id IN ({placeholders})", pks)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()

    return {
        "backup": backup_info,
        "deleted": sum(len(v) for v in by_table.values()),
    }
