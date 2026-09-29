"""复审 R06/R07/R09：终态、可执行向导、凭证不入库。"""
from __future__ import annotations

import unittest
import uuid

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.main import app


def _tool(rid: str, **extra) -> dict:
    mf = {
        "spec_version": "0.6.1",
        "resource_id": rid,
        "resource_type": "tool",
        "name": "http tool",
        "description": "d2",
        "version": "1.0.0",
        "owner": {"name": "t", "contact": "t", "email": "t@t.com"},
        "capabilities": {
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "call_mode": "sync",
            "idempotent": True,
            "timeout": 10,
            "side_effects": "none",
        },
        "interfaces": {"endpoint": "https://example.com/tool", "method": "POST", "auth_type": "none"},
    }
    mf.update(extra)
    return mf


class ExecutableRegisterTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_local_endpoint_rejected(self):
        rid = f"demo/local_{uuid.uuid4().hex[:6]}"
        mf = _tool(rid)
        mf["interfaces"] = {"endpoint": f"local://tool/{rid}", "method": "exec", "auth_type": "none"}
        reg = self.client.post("/api/resources/register", json={"manifest": mf}, headers=self.h)
        self.assertEqual(reg.status_code, 400, reg.text)
        self.assertIn("http", reg.text)

    def test_plaintext_token_rejected_and_ref_kept(self):
        rid = f"demo/sec_{uuid.uuid4().hex[:6]}"
        leaked = _tool(rid)
        leaked["interfaces"] = {
            "endpoint": "https://example.com/tool",
            "method": "POST",
            "auth": {"token": "super-secret"},
        }
        bad = self.client.post("/api/resources/register", json={"manifest": leaked}, headers=self.h)
        self.assertEqual(bad.status_code, 400, bad.text)
        self.assertIn("明文凭证", bad.text)

        ok_mf = _tool(rid)
        ok_mf["interfaces"] = {
            "endpoint": "https://example.com/tool",
            "method": "POST",
            "auth_type": "bearer",
            "auth": {"credential_ref": "TOOL_TOKEN"},
        }
        good = self.client.post("/api/resources/register", json={"manifest": ok_mf}, headers=self.h)
        self.assertEqual(good.status_code, 200, good.text)
        stored = good.json()["manifest"]
        self.assertEqual(stored["interfaces"]["auth"]["credential_ref"], "TOOL_TOKEN")
        self.assertNotIn("super-secret", str(stored))

    def test_skill_requires_chain(self):
        rid = f"demo/sk_{uuid.uuid4().hex[:6]}"
        mf = _tool(rid, resource_type="skill", name="skill")
        mf["interfaces"] = {"method": "workflow", "auth_type": "none"}
        missing = self.client.post("/api/resources/register", json={"manifest": mf}, headers=self.h)
        self.assertEqual(missing.status_code, 400, missing.text)
        mf["skill"] = {
            "execution_type": "workflow",
            "chain": [
                {"step_id": "s1", "resource_id": "builtin/exact_match"},
                {"step_id": "s2", "resource_id": "builtin/exact_match", "input": {"value": {"$ref": "s1.output"}}},
            ],
        }
        ok = self.client.post("/api/resources/register", json={"manifest": mf}, headers=self.h)
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(len(ok.json()["manifest"]["skill"]["chain"]), 2)


class SessionTerminalStateTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_running_task_is_not_implied_complete(self):
        import asyncio
        from app.database import async_session
        from app.models import AgentRun, AgentSession, EvalTask

        created = self.client.post(
            "/api/agents/sessions",
            json={"requirement": f"d2 {uuid.uuid4().hex[:6]}"},
            headers=self.h,
        )
        self.assertEqual(created.status_code, 200, created.text)
        sid = created.json()["id"]

        async def _attach():
            async with async_session() as db:
                session = await db.get(AgentSession, sid)
                task = EvalTask(name="still-running", dataset_id=0, model_id=0, status="running", report_path="")
                db.add(task)
                await db.flush()
                run = AgentRun(
                    session_id=sid,
                    status="success",
                    provider="live",
                    checkpoint_thread_id=f"thr-{uuid.uuid4().hex}",
                )
                db.add(run)
                await db.flush()
                session.task_id = task.id
                session.active_run_id = None
                await db.commit()
                return run.id, task.id

        run_id, _task_id = asyncio.run(_attach())
        detail = self.client.get(f"/api/agents/sessions/{sid}", headers=self.h)
        self.assertEqual(detail.status_code, 200, detail.text)
        body = detail.json()
        self.assertIsNone(body.get("active_run_id"))
        self.assertEqual(body.get("last_run_id"), run_id)
        self.assertEqual(body.get("task_status"), "running")
        self.assertEqual(body.get("report_status"), "missing")
        self.assertTrue(any(item["id"] == run_id for item in body.get("recent_runs") or []))
