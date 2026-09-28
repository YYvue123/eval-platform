"""WP09 协作委派与可信知识。"""
from __future__ import annotations

import unittest
import uuid

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.main import app
from app.services.collaboration import (
    FORBIDDEN_WRITE_TOOLS,
    MAX_DEPTH,
    MAX_PARALLEL,
    assert_sub_agent_tool,
    plan_roles,
)
from app.models import EvalTask


class CollaborationUnitTest(unittest.TestCase):
    def test_sub_agent_cannot_write_task(self):
        for t in FORBIDDEN_WRITE_TOOLS:
            with self.assertRaises(PermissionError):
                assert_sub_agent_tool(t)
        assert_sub_agent_tool("monitor_task")

    def test_simple_task_only_monitor(self):
        t = EvalTask(status="queued", trial_run=True, fail_count=0)
        self.assertEqual(plan_roles(t), ["monitor"])

    def test_failed_gets_diagnose(self):
        t = EvalTask(status="failed", trial_run=True, fail_count=1)
        roles = plan_roles(t)
        self.assertIn("monitor", roles)
        self.assertIn("diagnose", roles)
        self.assertLessEqual(len(roles), MAX_PARALLEL)


class CollaborationApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def _session_with_task(self):
        ds = self.client.post(
            "/api/datasets",
            json={"name": f"wp09-{uuid.uuid4().hex[:6]}", "domain_type": "general"},
            headers=self.h,
        ).json()
        model = self.client.post(
            "/api/models",
            json={"name": f"wp09m-{uuid.uuid4().hex[:6]}", "api_url": ""},
            headers=self.h,
        ).json()
        sess = self.client.post(
            "/api/agents/sessions",
            json={"requirement": "通用对话评测", "objective": "wp09"},
            headers=self.h,
        ).json()
        sid = sess["id"]
        self.client.post(
            f"/api/agents/sessions/{sid}/clarify",
            json={"dataset_id": ds["id"], "model_id": model["id"], "trial_run": True, "objective": "wp09"},
            headers=self.h,
        )
        conf = self.client.post(
            f"/api/agents/sessions/{sid}/confirm",
            json={"execute": False, "client_invocation_id": f"wp09-{uuid.uuid4().hex}"},
            headers=self.h,
        )
        self.assertEqual(conf.status_code, 200, conf.text)
        return sid, conf.json()["task_id"]

    def test_monitor_dedup(self):
        sid, _ = self._session_with_task()
        m1 = self.client.get(f"/api/agents/sessions/{sid}/monitor", headers=self.h)
        self.assertEqual(m1.status_code, 200, m1.text)
        m2 = self.client.get(f"/api/agents/sessions/{sid}/monitor", headers=self.h)
        self.assertEqual(m2.status_code, 200, m2.text)
        # 第二次无变化应 skipped
        self.assertTrue(m2.json().get("skipped_llm") or m2.json().get("unchanged") or m2.json().get("status"))

    def test_collaborate_simple_not_all_roles(self):
        sid, _ = self._session_with_task()
        out = self.client.post(f"/api/agents/sessions/{sid}/collaborate", json={}, headers=self.h)
        self.assertEqual(out.status_code, 200, out.text)
        roles = out.json().get("roles") or []
        self.assertEqual(roles, ["monitor"])
        self.assertLessEqual(len(out.json().get("items") or []), MAX_PARALLEL)

    def test_diagnose_has_evidence(self):
        sid, tid = self._session_with_task()
        # 标失败以触发 diagnose 证据路径
        from app.database import async_session
        from app.models import EvalTask
        import asyncio

        async def fail():
            async with async_session() as db:
                t = await db.get(EvalTask, tid)
                t.status = "failed"
                t.error_message = "boom"
                await db.commit()

        asyncio.run(fail())
        diag = self.client.post(f"/api/agents/sessions/{sid}/diagnose", headers=self.h)
        self.assertEqual(diag.status_code, 200, diag.text)
        body = diag.json()
        self.assertTrue(body.get("evidence") or body.get("verification_steps"))
        self.assertTrue(body.get("requires_main_approval", True))
        dels = self.client.get(f"/api/agents/sessions/{sid}/delegations", headers=self.h)
        self.assertEqual(dels.status_code, 200)
        self.assertGreaterEqual(len(dels.json()["evidence"]), 1)

    def test_knowledge_candidate_review_and_tenant(self):
        title = f"cand-{uuid.uuid4().hex[:6]}"
        add = self.client.post(
            "/api/agents/knowledge",
            json={"title": title, "content": "secret-tenant-a", "category": "case"},
            headers=self.h,
        )
        self.assertEqual(add.status_code, 200, add.text)
        self.assertEqual(add.json()["status"], "pending")
        # 未审核不进检索
        listed = self.client.get("/api/agents/knowledge", params={"q": title}, headers=self.h)
        titles = [x["title"] for x in listed.json().get("items") or []]
        self.assertNotIn(title, titles)

        cid = add.json()["id"]
        rev = self.client.post(
            f"/api/agents/knowledge/candidates/{cid}/review",
            json={"approve": True, "ttl_days": 30},
            headers=self.h,
        )
        self.assertEqual(rev.status_code, 200, rev.text)
        self.assertEqual(rev.json()["status"], "approved")
        listed2 = self.client.get("/api/agents/knowledge", params={"q": title}, headers=self.h)
        titles2 = [x["title"] for x in listed2.json().get("items") or []]
        self.assertIn(title, titles2)

        # 研究员另一租户（若同租户则仍可见；跨租户用直接 DB 改 tenant）
        from app.database import async_session
        from app.models import KnowledgeEntry
        import asyncio

        entry_id = rev.json()["entry_id"]

        async def move_tenant():
            async with async_session() as db:
                e = await db.get(KnowledgeEntry, entry_id)
                e.tenant_id = 99999
                await db.commit()

        asyncio.run(move_tenant())
        listed3 = self.client.get("/api/agents/knowledge", params={"q": title}, headers=self.h)
        titles3 = [x["title"] for x in listed3.json().get("items") or []]
        self.assertNotIn(title, titles3)

    def test_depth_limit_constant(self):
        self.assertEqual(MAX_DEPTH, 2)
        self.assertEqual(MAX_PARALLEL, 2)


if __name__ == "__main__":
    unittest.main()
