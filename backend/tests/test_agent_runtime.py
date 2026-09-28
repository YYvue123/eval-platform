"""U0 F01 Agent Runtime：禁止 mock；live + 规划模型 tool-calling。"""
from __future__ import annotations

import asyncio
import unittest
import uuid
from unittest.mock import AsyncMock, patch

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
        # 规划模型：仅占位 api_url，真实 HTTP 由 monkeypatch 拦截
        model = self.client.post(
            "/api/models",
            headers=self.h,
            json={
                "name": f"planner-{uuid.uuid4().hex[:6]}",
                "provider": "openai",
                "api_url": "https://example.invalid/v1",
                "api_key": "test-key",
                "served_model_name": "stub",
            },
        )
        self.assertEqual(model.status_code, 200, model.text)
        self.planner_id = model.json()["id"]

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def _llm_tool(self, query="评测"):
        return {
            "message": {},
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "search_knowledge", "arguments": dumps({"query": query})},
                }
            ],
            "content": "",
            "finish_reason": "tool_calls",
            "usage": {"total_tokens": 42},
            "tokens": 42,
            "latency_ms": 12,
            "mock": False,
        }

    def _llm_reply(self, text="完成"):
        return {
            "message": {"content": text},
            "tool_calls": [],
            "content": text,
            "finish_reason": "stop",
            "usage": {"total_tokens": 20},
            "tokens": 20,
            "latency_ms": 8,
            "mock": False,
        }

    def test_mock_provider_rejected(self):
        run = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "x", "provider": "mock", "planner_model_id": self.planner_id, "sync": False},
            headers=self.h,
        )
        self.assertEqual(run.status_code, 400, run.text)

    def test_missing_planner_rejected(self):
        run = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "x", "provider": "live", "sync": False},
            headers=self.h,
        )
        self.assertEqual(run.status_code, 400, run.text)

    def test_live_tool_loop_success(self):
        calls = {"n": 0}

        async def fake_invoke(model, messages, tools):
            calls["n"] += 1
            if calls["n"] == 1:
                return self._llm_tool("金融评测")
            return self._llm_reply("已检索知识")

        with patch("app.services.model_client.invoke_chat_tools", new=AsyncMock(side_effect=fake_invoke)):
            run = self.client.post(
                f"/api/agents/sessions/{self.sid}/runs",
                json={
                    "message": "金融评测知识检索",
                    "provider": "live",
                    "planner_model_id": self.planner_id,
                    "sync": True,
                },
                headers=self.h,
            )
        self.assertEqual(run.status_code, 200, run.text)
        data = run.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["provider"], "live")
        self.assertGreaterEqual(data["tokens_used"], 1)
        ev = self.client.get(f"/api/agents/runs/{data['id']}/events", headers=self.h)
        types = [e["type"] for e in ev.json()["items"]]
        self.assertIn("tool.selected", types)
        self.assertIn("tool.observed", types)
        self.assertIn("llm.reply", types)
        self.assertNotIn("provider.fallback_mock_select", types)

    def test_single_active_run_conflict(self):
        r1 = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "hold", "provider": "live", "planner_model_id": self.planner_id, "sync": False},
            headers=self.h,
        )
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertEqual(r1.json()["status"], "queued")
        r2 = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "second", "provider": "live", "planner_model_id": self.planner_id, "sync": False},
            headers=self.h,
        )
        self.assertEqual(r2.status_code, 409, r2.text)

    def test_cancel_queued(self):
        r1 = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "cancel me", "planner_model_id": self.planner_id, "sync": False},
            headers=self.h,
        )
        rid = r1.json()["id"]
        c = self.client.post(f"/api/agents/runs/{rid}/cancel", headers=self.h)
        self.assertEqual(c.status_code, 200, c.text)
        self.assertEqual(c.json()["status"], "cancelled")

    def test_budget_pause(self):
        async def fake_invoke(model, messages, tools):
            return {**self._llm_tool(), "tokens": 100}

        with patch("app.services.model_client.invoke_chat_tools", new=AsyncMock(side_effect=fake_invoke)):
            run = self.client.post(
                f"/api/agents/sessions/{self.sid}/runs",
                json={
                    "message": "预算",
                    "provider": "live",
                    "planner_model_id": self.planner_id,
                    "token_budget": 5,
                    "sync": True,
                },
                headers=self.h,
            )
        self.assertEqual(run.status_code, 200, run.text)
        self.assertEqual(run.json()["status"], "paused_budget")

    def test_checkpoint_resume(self):
        from app.database import async_session
        from app.models import AgentRun, AgentSession

        r1 = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "resume-demo", "planner_model_id": self.planner_id, "sync": False},
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
                    "pending_reply": "从 checkpoint 恢复",
                    "final_reply": "",
                })
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

        r1 = self.client.post(
            f"/api/agents/sessions/{self.sid}/runs",
            json={"message": "bad-tool", "planner_model_id": self.planner_id, "sync": False},
            headers=self.h,
        )
        rid = r1.json()["id"]

        async def prep():
            async with async_session() as db:
                run = await db.get(AgentRun, rid)
                run.status = "queued"
                run.checkpoint_json = dumps({
                    "schema_version": 1,
                    "phase": "observe",
                    "messages": [{"role": "user", "content": "x"}],
                    "pending_tool": {"name": "search_knowledge", "arguments": {"query": "ok", "evil": True}},
                    "observations": [],
                    "final_reply": "",
                })
                s = await db.get(AgentSession, self.sid)
                s.active_run_id = rid
                await db.commit()

        asyncio.run(prep())
        out = self.client.post(f"/api/agents/runs/{rid}/resume", headers=self.h)
        self.assertEqual(out.status_code, 200, out.text)
        self.assertEqual(out.json()["status"], "failed")
        self.assertEqual(out.json()["error_code"], "tool_failed")


if __name__ == "__main__":
    unittest.main()
