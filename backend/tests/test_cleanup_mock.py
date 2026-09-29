from tests import isolated_env  # noqa: F401

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.isolated_env import assert_isolated_database

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cleanup_mock.fingerprint import (
    canonical_json,
    file_sha256,
    manifest_hash,
    resolve_sqlite_path,
    target_fingerprint,
)


class FingerprintTests(unittest.TestCase):
    def test_resolve_rejects_business_eval_platform_name_in_tests(self):
        url = os.environ["DATABASE_URL"]
        db_path = assert_isolated_database(url)
        resolved = resolve_sqlite_path(url)
        self.assertEqual(resolved, db_path)
        self.assertNotEqual(resolved.name, "eval_platform.db")

    def test_resolve_sqlite_path_strips_url_prefix(self):
        d = Path(tempfile.mkdtemp())
        p = d / "sample.db"
        p.write_bytes(b"x")
        url = "sqlite+aiosqlite:///" + p.as_posix()
        self.assertEqual(resolve_sqlite_path(url), p.resolve())
        self.assertEqual(resolve_sqlite_path(str(p)), p.resolve())

    def test_fingerprint_changes_when_bytes_change(self):
        d = Path(tempfile.mkdtemp())
        p = d / "t.db"
        p.write_bytes(b"abc")
        a = target_fingerprint(p)
        digest_a = file_sha256(p)
        self.assertEqual(digest_a, hashlib.sha256(b"abc").hexdigest())
        p.write_bytes(b"abcd")
        b = target_fingerprint(p)
        self.assertTrue(a.startswith("sha256:"))
        self.assertEqual(len(a), len("sha256:") + 64)
        self.assertNotEqual(a, b)
        inner = digest_a + "|" + str(p.resolve())
        self.assertEqual(a, "sha256:" + hashlib.sha256(inner.encode("utf-8")).hexdigest())

    def test_manifest_hash_ignores_own_field(self):
        body = {"actions": [{"pk": 1}], "manifest_hash": "x"}
        dumped = canonical_json({"actions": [{"pk": 1}]})
        self.assertEqual(dumped, json.dumps({"actions": [{"pk": 1}]}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        h1 = manifest_hash(body)
        h2 = manifest_hash({"actions": [{"pk": 1}]})
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, "x")
        self.assertEqual(h1, hashlib.sha256(dumped.encode("utf-8")).hexdigest())


class BackupTests(unittest.TestCase):
    def test_backup_hash_matches_restore_copy(self):
        import sqlite3
        from tools.cleanup_mock.backup_sqlite import consistent_backup

        d = Path(tempfile.mkdtemp())
        src = d / "src.db"
        dest = d / "dst.db"
        conn = sqlite3.connect(src)
        conn.execute("CREATE TABLE t(id INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()
        conn.close()
        info = consistent_backup(src, dest)
        self.assertTrue(dest.exists())
        self.assertEqual(info["sha256"], file_sha256(dest))
        self.assertEqual(info["path"], str(dest.resolve()))
        self.assertEqual(info["source"], str(src.resolve()))
        self.assertEqual(info["size"], dest.stat().st_size)
        c = sqlite3.connect(dest)
        n = c.execute("SELECT COUNT(*) FROM t").fetchone()[0]
        c.close()
        self.assertEqual(n, 1)


class PlanTests(unittest.TestCase):
    def test_plan_does_not_write(self):
        import sqlite3
        from tools.cleanup_mock.inventory import build_plan

        d = Path(tempfile.mkdtemp())
        db = d / "p.db"
        c = sqlite3.connect(db)
        c.executescript("""
        CREATE TABLE eval_tasks (id INTEGER PRIMARY KEY, status TEXT, simulation INTEGER, trial_run INTEGER);
        CREATE TABLE eval_results (id INTEGER PRIMARY KEY, task_id INTEGER, simulation INTEGER);
        CREATE TABLE eval_lineages (id INTEGER PRIMARY KEY, task_id INTEGER);
        CREATE TABLE agent_runs (id INTEGER PRIMARY KEY, provider TEXT, session_id INTEGER);
        CREATE TABLE agent_events (id INTEGER PRIMARY KEY, run_id INTEGER);
        INSERT INTO eval_tasks VALUES (1,'success',1,0);
        INSERT INTO eval_tasks VALUES (2,'success',0,1);
        INSERT INTO eval_results VALUES (10,1,1);
        INSERT INTO eval_results VALUES (11,2,0);
        INSERT INTO eval_lineages VALUES (3,1);
        INSERT INTO agent_runs VALUES (5,'mock',1);
        INSERT INTO agent_events VALUES (6,5);
        """)
        c.commit()
        c.close()
        plan = build_plan(db)
        after = sqlite3.connect(db)
        n = after.execute("SELECT COUNT(*) FROM eval_results").fetchone()[0]
        n_tasks = after.execute("SELECT COUNT(*) FROM eval_tasks").fetchone()[0]
        n_lineages = after.execute("SELECT COUNT(*) FROM eval_lineages").fetchone()[0]
        n_runs = after.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
        n_events = after.execute("SELECT COUNT(*) FROM agent_events").fetchone()[0]
        after.close()
        self.assertEqual(n, 2)
        self.assertEqual(n_tasks, 2)
        self.assertEqual(n_lineages, 1)
        self.assertEqual(n_runs, 1)
        self.assertEqual(n_events, 1)
        tables = {a["table"] for a in plan["actions"]}
        self.assertIn("eval_results", tables)
        self.assertIn("eval_tasks", tables)
        self.assertIn("agent_runs", tables)
        self.assertIn("eval_lineages", tables)
        self.assertIn("agent_events", tables)
        pks_tasks = {a["pk"] for a in plan["actions"] if a["table"] == "eval_tasks"}
        self.assertIn(1, pks_tasks)
        self.assertNotIn(2, pks_tasks)
        result_pks = {a["pk"] for a in plan["actions"] if a["table"] == "eval_results"}
        self.assertEqual(result_pks, {10})
        self.assertTrue(all(a["action"] == "delete" for a in plan["actions"]))
        self.assertTrue(plan["manifest_hash"])
        self.assertEqual(plan["manifest_hash"], manifest_hash(plan))
        self.assertEqual(plan["target"]["absolute_path"], str(db.resolve()))
        self.assertEqual(plan["target"]["fingerprint"], target_fingerprint(db))
        self.assertEqual(plan["counts_before"]["eval_results"], 2)
        self.assertEqual(plan["counts_before"]["eval_tasks"], 2)
        self.assertEqual(plan["counts_before"]["agent_runs"], 1)

    def test_plan_notes_missing_tables_and_columns(self):
        import sqlite3
        from tools.cleanup_mock.inventory import build_plan

        d = Path(tempfile.mkdtemp())
        db = d / "partial.db"
        c = sqlite3.connect(db)
        c.executescript("""
        CREATE TABLE eval_tasks (id INTEGER PRIMARY KEY, status TEXT);
        INSERT INTO eval_tasks VALUES (1,'success');
        """)
        c.commit()
        c.close()
        plan = build_plan(db)
        after = sqlite3.connect(db)
        n = after.execute("SELECT COUNT(*) FROM eval_tasks").fetchone()[0]
        after.close()
        self.assertEqual(n, 1)
        self.assertEqual(plan["actions"], [])
        notes = " ".join(plan["notes"])
        self.assertTrue(notes)
        self.assertIn("eval_tasks", notes)
        self.assertIn("simulation", notes)


class ApplyTests(unittest.TestCase):
    def _seed(self, extra_sql=""):
        import sqlite3

        d = Path(tempfile.mkdtemp())
        db = d / "p.db"
        c = sqlite3.connect(db)
        c.executescript("""
        CREATE TABLE eval_tasks (id INTEGER PRIMARY KEY, status TEXT, simulation INTEGER, trial_run INTEGER);
        CREATE TABLE eval_results (id INTEGER PRIMARY KEY, task_id INTEGER, simulation INTEGER);
        CREATE TABLE eval_lineages (id INTEGER PRIMARY KEY, task_id INTEGER);
        CREATE TABLE agent_runs (id INTEGER PRIMARY KEY, provider TEXT, session_id INTEGER);
        CREATE TABLE agent_events (id INTEGER PRIMARY KEY, run_id INTEGER);
        INSERT INTO eval_tasks VALUES (1,'success',1,0);
        INSERT INTO eval_tasks VALUES (2,'success',0,1);
        INSERT INTO eval_results VALUES (10,1,1);
        INSERT INTO eval_results VALUES (11,2,0);
        INSERT INTO eval_lineages VALUES (3,1);
        INSERT INTO agent_runs VALUES (5,'mock',1);
        INSERT INTO agent_events VALUES (6,5);
        """)
        if extra_sql:
            c.executescript(extra_sql)
        c.commit()
        c.close()
        return db

    def test_apply_rejects_wrong_hash(self):
        from tools.cleanup_mock.inventory import build_plan
        from tools.cleanup_mock.apply import apply_plan
        db = self._seed()
        plan = build_plan(db)
        plan["manifest_hash"] = "deadbeef"
        with self.assertRaises(ValueError) as ctx:
            apply_plan(db, plan, confirm_fingerprint=plan["target"]["fingerprint"], backup_dir=db.parent / "b")
        self.assertIn("manifest", str(ctx.exception).lower())
        c = __import__("sqlite3").connect(db)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eval_results").fetchone()[0], 2)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eval_tasks").fetchone()[0], 2)
        c.close()

    def test_apply_rejects_wrong_fingerprint(self):
        from tools.cleanup_mock.inventory import build_plan
        from tools.cleanup_mock.apply import apply_plan
        db = self._seed()
        plan = build_plan(db)
        with self.assertRaises(ValueError) as ctx:
            apply_plan(db, plan, confirm_fingerprint="sha256:" + "0" * 64, backup_dir=db.parent / "b")
        self.assertIn("fingerprint", str(ctx.exception).lower())
        c = __import__("sqlite3").connect(db)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eval_tasks").fetchone()[0], 2)
        c.close()

    def test_apply_rejects_missing_confirm(self):
        from tools.cleanup_mock.inventory import build_plan
        from tools.cleanup_mock.apply import apply_plan
        db = self._seed()
        plan = build_plan(db)
        with self.assertRaises(ValueError) as ctx:
            apply_plan(db, plan, confirm_fingerprint="", backup_dir=db.parent / "b")
        self.assertIn("confirm", str(ctx.exception).lower())

    def test_apply_rejects_busy_status(self):
        from tools.cleanup_mock.inventory import build_plan
        from tools.cleanup_mock.apply import apply_plan
        db = self._seed("UPDATE eval_tasks SET status='running' WHERE id=2;")
        plan = build_plan(db)
        with self.assertRaises(ValueError) as ctx:
            apply_plan(db, plan, confirm_fingerprint=plan["target"]["fingerprint"], backup_dir=db.parent / "b")
        msg = str(ctx.exception).lower()
        self.assertTrue("running" in msg or "status" in msg or "queued" in msg)
        c = __import__("sqlite3").connect(db)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eval_tasks WHERE id=1").fetchone()[0], 1)
        c.close()

    def test_apply_deletes_simulation_keeps_trial(self):
        from tools.cleanup_mock.inventory import build_plan
        from tools.cleanup_mock.apply import apply_plan
        db = self._seed()
        plan = build_plan(db)
        result = apply_plan(db, plan, confirm_fingerprint=plan["target"]["fingerprint"], backup_dir=db.parent / "b")
        self.assertTrue((db.parent / "b").exists())
        self.assertIn("backup", result)
        c = __import__("sqlite3").connect(db)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eval_tasks WHERE id=2").fetchone()[0], 1)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eval_tasks WHERE id=1").fetchone()[0], 0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eval_results WHERE simulation=1").fetchone()[0], 0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eval_results WHERE id=11").fetchone()[0], 1)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eval_lineages").fetchone()[0], 0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_runs WHERE provider='mock'").fetchone()[0], 0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_events").fetchone()[0], 0)
        c.close()


class VerifyTests(unittest.TestCase):
    def _seed(self):
        import sqlite3

        d = Path(tempfile.mkdtemp())
        db = d / "p.db"
        c = sqlite3.connect(db)
        c.executescript("""
        CREATE TABLE eval_tasks (id INTEGER PRIMARY KEY, status TEXT, simulation INTEGER, trial_run INTEGER);
        CREATE TABLE eval_results (id INTEGER PRIMARY KEY, task_id INTEGER, simulation INTEGER);
        CREATE TABLE eval_lineages (id INTEGER PRIMARY KEY, task_id INTEGER);
        CREATE TABLE agent_runs (id INTEGER PRIMARY KEY, provider TEXT, session_id INTEGER);
        CREATE TABLE agent_events (id INTEGER PRIMARY KEY, run_id INTEGER);
        INSERT INTO eval_tasks VALUES (1,'success',1,0);
        INSERT INTO eval_tasks VALUES (2,'success',0,1);
        INSERT INTO eval_results VALUES (10,1,1);
        INSERT INTO eval_results VALUES (11,2,0);
        INSERT INTO eval_lineages VALUES (3,1);
        INSERT INTO agent_runs VALUES (5,'mock',1);
        INSERT INTO agent_events VALUES (6,5);
        """)
        c.commit()
        c.close()
        return db

    def test_dirty_fixture_not_ok(self):
        from tools.cleanup_mock.verify import verify_clean

        db = self._seed()
        report = verify_clean(db)
        self.assertFalse(report["ok"])
        self.assertGreater(report["simulation_results"], 0)
        self.assertGreater(report["simulation_tasks"], 0)
        self.assertGreater(report["mock_runs"], 0)
        self.assertIn("integrity", report)
        self.assertIn("foreign_key", report)

    def test_after_apply_plan_ok(self):
        from tools.cleanup_mock.inventory import build_plan
        from tools.cleanup_mock.apply import apply_plan
        from tools.cleanup_mock.verify import verify_clean

        db = self._seed()
        dirty = verify_clean(db)
        self.assertFalse(dirty["ok"])
        plan = build_plan(db)
        apply_plan(
            db,
            plan,
            confirm_fingerprint=plan["target"]["fingerprint"],
            backup_dir=db.parent / "b",
        )
        report = verify_clean(db)
        self.assertTrue(report["ok"])
        self.assertEqual(report["simulation_results"], 0)
        self.assertEqual(report["simulation_tasks"], 0)
        self.assertEqual(report["mock_runs"], 0)
        self.assertEqual(report["integrity"], "ok")
        self.assertEqual(report["foreign_key"], [])


class SeedTests(unittest.TestCase):
    def test_seed_db_does_not_insert_pack_datasets(self):
        import asyncio
        from sqlalchemy import select, func
        from app.database import Base, async_session, engine, init_db, seed_db
        from app.models import Dataset, KnowledgeEntry

        url = os.environ["DATABASE_URL"]
        assert_isolated_database(url)

        async def run():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await init_db()
            await seed_db()
            async with async_session() as db:
                packs = await db.scalar(
                    select(func.count()).select_from(Dataset).where(Dataset.name.like("pack:%"))
                )
                sample_titles = (
                    await db.execute(
                        select(KnowledgeEntry.title).where(
                            KnowledgeEntry.title.in_(
                                ["任务失败不自动恢复", "内置裁判画像"]
                            )
                        )
                    )
                ).scalars().all()
                templates = await db.scalar(
                    select(func.count())
                    .select_from(KnowledgeEntry)
                    .where(KnowledgeEntry.ref_type == "template")
                )
                return (packs or 0), list(sample_titles), (templates or 0)

        packs, sample_titles, templates = asyncio.run(run())
        self.assertEqual(packs, 0)
        self.assertEqual(sample_titles, [])
        self.assertGreater(templates, 0)


class CliTests(unittest.TestCase):
    def _seed(self):
        d = Path(tempfile.mkdtemp())
        db = d / "p.db"
        c = sqlite3.connect(db)
        c.executescript("""
        CREATE TABLE eval_tasks (id INTEGER PRIMARY KEY, status TEXT, simulation INTEGER, trial_run INTEGER);
        CREATE TABLE eval_results (id INTEGER PRIMARY KEY, task_id INTEGER, simulation INTEGER);
        CREATE TABLE eval_lineages (id INTEGER PRIMARY KEY, task_id INTEGER);
        CREATE TABLE agent_runs (id INTEGER PRIMARY KEY, provider TEXT, session_id INTEGER);
        CREATE TABLE agent_events (id INTEGER PRIMARY KEY, run_id INTEGER);
        INSERT INTO eval_tasks VALUES (1,'success',1,0);
        INSERT INTO eval_tasks VALUES (2,'success',0,1);
        INSERT INTO eval_results VALUES (10,1,1);
        INSERT INTO eval_results VALUES (11,2,0);
        INSERT INTO eval_lineages VALUES (3,1);
        INSERT INTO agent_runs VALUES (5,'mock',1);
        INSERT INTO agent_events VALUES (6,5);
        """)
        c.commit()
        c.close()
        return db

    def _run(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        return subprocess.run(
            [sys.executable, "-m", "tools.cleanup_mock", *args],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
        )

    def test_plan_cli_does_not_write(self):
        db = self._seed()
        out = db.parent / "plan.json"
        before_mtime = db.stat().st_mtime_ns
        before_hash = hashlib.sha256(db.read_bytes()).hexdigest()
        c = sqlite3.connect(db)
        before_counts = {
            "eval_tasks": c.execute("SELECT COUNT(*) FROM eval_tasks").fetchone()[0],
            "eval_results": c.execute("SELECT COUNT(*) FROM eval_results").fetchone()[0],
            "eval_lineages": c.execute("SELECT COUNT(*) FROM eval_lineages").fetchone()[0],
            "agent_runs": c.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0],
            "agent_events": c.execute("SELECT COUNT(*) FROM agent_events").fetchone()[0],
        }
        c.close()
        proc = self._run("plan", "--db", str(db), "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        combined = proc.stdout + proc.stderr
        self.assertNotIn("DATABASE_URL", combined)
        self.assertIn(str(db.resolve()), proc.stdout)
        self.assertTrue(out.exists())
        plan = json.loads(out.read_text(encoding="utf-8"))
        self.assertTrue(plan["actions"])
        self.assertEqual(db.stat().st_mtime_ns, before_mtime)
        self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), before_hash)
        c = sqlite3.connect(db)
        for table, n in before_counts.items():
            self.assertEqual(c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], n)
        c.close()

    def test_apply_cli_without_confirm_exits_nonzero(self):
        db = self._seed()
        manifest = db.parent / "plan.json"
        proc_plan = self._run("plan", "--db", str(db), "--out", str(manifest))
        self.assertEqual(proc_plan.returncode, 0, proc_plan.stderr)
        proc = self._run(
            "apply",
            "--db", str(db),
            "--manifest", str(manifest),
            "--backup-dir", str(db.parent / "b"),
        )
        self.assertNotEqual(proc.returncode, 0)
        combined = proc.stdout + proc.stderr
        self.assertNotIn("DATABASE_URL", combined)
        c = sqlite3.connect(db)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eval_tasks").fetchone()[0], 2)
        c.close()

    def test_apply_verify_backup_cli(self):
        from tools.cleanup_mock.fingerprint import target_fingerprint

        db = self._seed()
        manifest = db.parent / "plan.json"
        backup_file = db.parent / "copy.db"
        proc_plan = self._run("plan", "--db", str(db), "--out", str(manifest))
        self.assertEqual(proc_plan.returncode, 0, proc_plan.stderr)
        plan = json.loads(manifest.read_text(encoding="utf-8"))
        fp = plan["target"]["fingerprint"]
        self.assertEqual(fp, target_fingerprint(db))
        proc_backup = self._run("backup", "--db", str(db), "--out", str(backup_file))
        self.assertEqual(proc_backup.returncode, 0, proc_backup.stderr)
        self.assertTrue(backup_file.exists())
        bc = sqlite3.connect(backup_file)
        self.assertEqual(bc.execute("SELECT COUNT(*) FROM eval_tasks").fetchone()[0], 2)
        bc.close()
        self.assertIn(str(db.resolve()), proc_backup.stdout)
        self.assertNotIn("DATABASE_URL", proc_backup.stdout + proc_backup.stderr)
        proc_apply = self._run(
            "apply",
            "--db", str(db),
            "--manifest", str(manifest),
            "--confirm-fingerprint", fp,
            "--backup-dir", str(db.parent / "b"),
        )
        self.assertEqual(proc_apply.returncode, 0, proc_apply.stderr)
        self.assertIn(str(db.resolve()), proc_apply.stdout)
        self.assertNotIn("DATABASE_URL", proc_apply.stdout + proc_apply.stderr)
        proc_verify = self._run("verify", "--db", str(db))
        self.assertEqual(proc_verify.returncode, 0, proc_verify.stderr)
        self.assertIn(str(db.resolve()), proc_verify.stdout)
        self.assertNotIn("DATABASE_URL", proc_verify.stdout + proc_verify.stderr)
        report = json.loads(proc_verify.stdout.strip().splitlines()[-1])
        self.assertTrue(report["ok"])


if __name__ == "__main__":
    unittest.main()
