from __future__ import annotations

import sqlite3
from pathlib import Path

from tools.cleanup_mock.fingerprint import manifest_hash, resolve_sqlite_path, target_fingerprint

KNOWN_TABLES = (
    "eval_tasks",
    "eval_results",
    "eval_lineages",
    "task_events",
    "task_subtasks",
    "report_jobs",
    "agent_runs",
    "agent_events",
    "agent_messages",
)

TASK_CHILD_TABLES = (
    "eval_lineages",
    "task_events",
    "task_subtasks",
    "report_jobs",
)


def _open_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    try:
        return sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError:
        return sqlite3.connect(str(path))


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _add_action(actions: list[dict], seen: set[tuple], table: str, pk: int, reason: str) -> None:
    key = (table, pk)
    if key in seen:
        return
    seen.add(key)
    actions.append({"table": table, "pk": pk, "action": "delete", "reason": reason})


def build_plan(db_path: Path) -> dict:
    path = resolve_sqlite_path(str(db_path))
    notes: list[str] = []
    actions: list[dict] = []
    seen: set[tuple] = set()
    counts_before: dict[str, int] = {}

    conn = _open_readonly(path)
    try:
        present = _table_names(conn)
        for table in KNOWN_TABLES:
            if table in present:
                counts_before[table] = _count(conn, table)
            else:
                notes.append(f"skip missing table {table}")

        if "eval_results" in present:
            cols = _columns(conn, "eval_results")
            if "simulation" not in cols:
                notes.append("eval_results missing column simulation")
            else:
                rows = conn.execute(
                    "SELECT id FROM eval_results WHERE simulation = 1"
                ).fetchall()
                for (pk,) in rows:
                    _add_action(actions, seen, "eval_results", pk, "eval_results.simulation=1")

        sim_task_ids: list[int] = []
        if "eval_tasks" in present:
            cols = _columns(conn, "eval_tasks")
            if "simulation" not in cols:
                notes.append("eval_tasks missing column simulation")
            else:
                rows = conn.execute("SELECT id FROM eval_tasks WHERE simulation = 1").fetchall()
                sim_task_ids = [pk for (pk,) in rows]
                for pk in sim_task_ids:
                    _add_action(actions, seen, "eval_tasks", pk, "eval_tasks.simulation=1")
        for child in TASK_CHILD_TABLES:
            if not sim_task_ids:
                continue
            if child not in present:
                continue
            cols = _columns(conn, child)
            if "task_id" not in cols:
                notes.append(f"{child} missing column task_id")
                continue
            placeholders = ",".join("?" * len(sim_task_ids))
            rows = conn.execute(
                f"SELECT id FROM {child} WHERE task_id IN ({placeholders})",
                sim_task_ids,
            ).fetchall()
            for (pk,) in rows:
                _add_action(
                    actions,
                    seen,
                    child,
                    pk,
                    f"{child} lineage of eval_tasks.simulation=1",
                )

        mock_run_ids: list[int] = []
        mock_session_ids: list[int] = []
        if "agent_runs" in present:
            cols = _columns(conn, "agent_runs")
            if "provider" not in cols:
                notes.append("agent_runs missing column provider")
            else:
                select = "SELECT id"
                if "session_id" in cols:
                    select += ", session_id"
                select += " FROM agent_runs WHERE provider = 'mock'"
                rows = conn.execute(select).fetchall()
                for row in rows:
                    pk = row[0]
                    mock_run_ids.append(pk)
                    if "session_id" in cols:
                        mock_session_ids.append(row[1])
                    _add_action(actions, seen, "agent_runs", pk, "agent_runs.provider=mock")

        if mock_run_ids and "agent_events" in present:
            cols = _columns(conn, "agent_events")
            if "run_id" not in cols:
                notes.append("agent_events missing column run_id")
            else:
                placeholders = ",".join("?" * len(mock_run_ids))
                rows = conn.execute(
                    f"SELECT id FROM agent_events WHERE run_id IN ({placeholders})",
                    mock_run_ids,
                ).fetchall()
                for (pk,) in rows:
                    _add_action(
                        actions,
                        seen,
                        "agent_events",
                        pk,
                        "agent_events of agent_runs.provider=mock",
                    )
        if mock_session_ids and "agent_messages" in present:
            cols = _columns(conn, "agent_messages")
            if "session_id" not in cols:
                notes.append("agent_messages missing column session_id")
            else:
                placeholders = ",".join("?" * len(mock_session_ids))
                rows = conn.execute(
                    f"SELECT id FROM agent_messages WHERE session_id IN ({placeholders})",
                    mock_session_ids,
                ).fetchall()
                for (pk,) in rows:
                    _add_action(
                        actions,
                        seen,
                        "agent_messages",
                        pk,
                        "agent_messages of agent_runs.provider=mock",
                    )
    finally:
        conn.close()

    plan = {
        "target": {
            "absolute_path": str(path),
            "fingerprint": target_fingerprint(path),
        },
        "counts_before": counts_before,
        "actions": actions,
        "notes": notes,
    }
    plan["manifest_hash"] = manifest_hash(plan)
    return plan
