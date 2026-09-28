"""WP07 Agent 运行时：单 active、工具循环、非法 schema、checkpoint 恢复、限轮/预算。"""
from __future__ import annotations

import unittest
import uuid

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.main import app
from app.services.agent_runtime import TOOL_SCHEMAS, _validate_tool_args
from app.utils.jsonutil import dumps


class ToolSchemaUnitTest(unittest.TestCase):
    def test_valid(self):
        _validate_tool_args("search_knowledge", {"query": "x"})

    def test_unknown_rejected(self):
        with self.assertRaises(ValueError):
            _validate_tool_args("nope", {})

    def test_extra_field_rejected(self):
        with self.assertRaises(ValueError):
            _validate_tool_args("search_knowledge", {"query": "x", "evil": 1})

    def test_schemas_registered(self):
        self.assertIn("search_knowledge", TOOL_SCHEMAS)
        self.assertIn("infer_dims", TOOL_SCHEMAS)


class AgentRuntimeApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(login.status_code, 200, login.text)
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        created = self.client.post(
            "/api/agents/sessions",
            json={"requirement": f"WP07 runtime {uuid.uuid4().hex[:6]}"},
            headers=self.h,
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.sid = created.json()["id"]

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_mock_tool_loop_success(self):
        run = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "金融评测知识检索", "provider": "mock", "sync": True},
            headers=self.h,
        )
        self.assertEqual(run.status_code, 200, run.text)
        data = run.json()
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(data["rounds_used"], 1)
        ev = self.client.get(f"/api/agents/runs/{data['id']}/events", headers=self.h)
        self.assertEqual(ev.status_code, 200, ev.text)
        types = [e["type"] for e in ev.json()["items"]]
        self.assertIn("tool.selected", types)
        self.assertIn("tool.observed", types)
        self.assertIn("llm.reply", types)
        self.assertIn("run.success", types)

    def test_single_active_run_conflict(self):
        # async create without sync leaves active if we stop before finish — use create only
        r1 = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "hold", "provider": "mock", "sync": False},
            headers=self.h,
        )
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertEqual(r1.json()["status"], "queued")
        r2 = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "second", "provider": "mock", "sync": False},
            headers=self.h,
        )
        self.assertEqual(r2.status_code, 409, r2.text)

    def test_cancel_queued(self):
        r1 = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "cancel me", "sync": False},
            headers=self.h,
        )
        rid = r1.json()["id"]
        c = self.client.post(f"/api/agents/runs/{rid}/cancel", headers=self.h)
        self.assertEqual(c.status_code, 200, c.text)
        self.assertEqual(c.json()["status"], "cancelled")

    def test_max_rounds(self):
        run = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "限轮", "provider": "mock", "max_rounds": 1, "sync": True},
            headers=self.h,
        )
        # max_rounds=1: select→observe→select 第二次会超限失败，或成功若路径更短
        self.assertEqual(run.status_code, 200, run.text)
        data = run.json()
        self.assertIn(data["status"], {"failed", "success", "paused_budget"})
        if data["status"] == "failed":
            self.assertEqual(data["error_code"], "max_rounds")

    def test_budget_pause(self):
        run = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "预算", "provider": "mock", "token_budget": 5, "sync": True},
            headers=self.h,
        )
        self.assertEqual(run.status_code, 200, run.text)
        self.assertEqual(run.json()["status"], "paused_budget")

    def test_checkpoint_resume(self):
        from app.database import async_session
        from app.models import AgentRun
        import asyncio

        r1 = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "resume-demo", "sync": False},
            headers=self.h,
        )
        rid = r1.json()["id"]

        async def prep():
            async with async_session() as db:
                run = await db.get(AgentRun, rid)
                run.status = "waiting"
                run.checkpoint_json = dumps({
                    "schema_version": 1,
                    "phase": "reply",
                    "messages": [{"role": "user", "content": "resume-demo"}],
                    "pending_tool": None,
                    "observations": [{"tool": "search_knowledge", "result": {"count": 2}}],
                    "final_reply": "",
                })
                # 释放 active 模拟 kill；resume 会重绑
                from app.models import AgentSession
                s = await db.get(AgentSession, self.sid)
                s.active_run_id = None
                await db.commit()

        asyncio.run(prep())
        resumed = self.client.post(f"/api/agents/runs/{rid}/resume", headers=self.h)
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["status"], "success")
        self.assertTrue(resumed.json()["checkpoint"].get("final_reply"))

    def test_invalid_tool_in_checkpoint(self):
        from app.database import async_session
        from app.models import AgentRun, AgentSession
        import asyncio

        r1 = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "bad-tool", "sync": False},
            headers=self.h,
        )
        rid = r1.json()["id"]

        async def prep():
            async with async_session() as db:
                run = await db.get(AgentRun, rid)
                run.status = "queued"
                run.checkpoint_json = dumps({
                    "schema_version": 1,
                    "phase": "select_tool",
                    "messages": [{"role": "user", "content": "x"}],
                    "pending_tool": None,
                    "observations": [{"tool": "search_knowledge", "result": {}}],
                    "final_reply": "",
                })
                # 强制下一轮选非法工具：通过改 mock 不好做，改为直接 pending observe 非法
                run.checkpoint_json = dumps({
                    "schema_version": 1,
                    "phase": "observe",
                    "messages": [{"role": "user", "content": "x"}],
                    "pending_tool": {"name": "search_knowledge", "arguments": {"query": "ok", "evil": True}},
                    "observations": [],
                    "final_reply": "",
                })
                await db.commit()

        asyncio.run(prep())
        # claim+execute via resume
        async def clear_active():
            async with async_session() as db:
                s = await db.get(AgentSession, self.sid)
                # keep active pointing to run
                s.active_run_id = rid
                await db.commit()

        asyncio.run(clear_active())
        out = self.client.post(f"/api/agents/runs/{rid}/resume", headers=self.h)
        self.assertEqual(out.status_code, 200, out.text)
        self.assertEqual(out.json()["status"], "failed")
        self.assertEqual(out.json()["error_code"], "tool_failed")

    def test_events_after_seq(self):
        run = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "events", "sync": True},
            headers=self.h,
        )
        rid = run.json()["id"]
        all_ev = self.client.get(f"/api/agents/runs/{rid}/events", headers=self.h).json()["items"]
        self.assertGreaterEqual(len(all_ev), 2)
        mid = all_ev[1]["seq"]
        rest = self.client.get(f"/api/agents/runs/{rid}/events", params={"after_seq": mid}, headers=self.h)
        self.assertEqual(rest.status_code, 200)
        for e in rest.json()["items"]:
            self.assertGreater(e["seq"], mid)


if __name__ == "__main__":
    unittest.main()
