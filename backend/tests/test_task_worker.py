"""WP04：claim 互斥、取消、重试、依赖环。"""
from __future__ import annotations

import asyncio
import json
import time
import unittest
import uuid

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.database import async_session, init_db
from app.main import app
from app.models import EvalTask
from app.services.task_service import claim_task, detect_dependency_cycle


class TaskWorkerClaimTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()

    async def test_double_claim_only_one_wins(self):
        async with async_session() as db:
            t = EvalTask(name=f"claim-{uuid.uuid4().hex[:6]}", dataset_id=1, model_id=1, status="queued")
            db.add(t)
            await db.commit()
            tid = t.id

        async with async_session() as db1:
            c1, tok1 = await claim_task(db1, tid, owner="w1")
            await db1.commit()
        async with async_session() as db2:
            c2, tok2 = await claim_task(db2, tid, owner="w2")
            await db2.commit()
        self.assertIsNotNone(c1)
        self.assertTrue(tok1)
        self.assertIsNone(c2)
        self.assertEqual(tok2, 0)

    async def test_dependency_cycle_detected(self):
        async with async_session() as db:
            a = EvalTask(name="a", dataset_id=1, model_id=1, status="draft")
            b = EvalTask(name="b", dataset_id=1, model_id=1, status="draft")
            db.add_all([a, b])
            await db.flush()
            a.depends_on_id = b.id
            b.depends_on_id = a.id
            await db.commit()
            aid, bid = a.id, b.id
        async with async_session() as db:
            self.assertTrue(await detect_dependency_cycle(db, aid, bid))


class TaskWorkerApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def _prep_trial_task(self):
        ds = self.client.post("/api/datasets", json={"name": f"w-{int(time.time()*1000)}"}, headers=self.h).json()
        payload = json.dumps([{"input": "1", "reference": "1"}, {"input": "2", "reference": "2"}]).encode()
        self.client.post(
            f"/api/datasets/{ds['id']}/import",
            headers=self.h,
            files={"file": ("qa.json", payload, "application/json")},
        )
        model = self.client.post(
            "/api/models", json={"name": f"m-{uuid.uuid4().hex[:6]}", "api_url": ""}, headers=self.h
        ).json()
        task = self.client.post(
            "/api/tasks",
            json={
                "name": f"t-{uuid.uuid4().hex[:6]}",
                "dataset_id": ds["id"],
                "model_id": model["id"],
                "judge_resource_id": "builtin/exact_match",
                "trial_run": True,
            },
            headers=self.h,
        )
        self.assertEqual(task.status_code, 200, task.text)
        return task.json()["id"]

    def test_retry_increments_attempt(self):
        tid = self._prep_trial_task()
        self.client.post(f"/api/tasks/{tid}/run", headers=self.h)
        detail = {}
        for _ in range(50):
            detail = self.client.get(f"/api/tasks/{tid}", headers=self.h).json()
            if detail["status"] in {"success", "failed", "partial_failed", "cancelled"}:
                break
            time.sleep(0.1)
        self.assertIn(detail["status"], {"success", "failed", "partial_failed", "cancelled"}, detail)
        retry = self.client.post(f"/api/tasks/{tid}/retry", headers=self.h)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertGreaterEqual(retry.json().get("attempt") or 0, 1)

    def test_cancel_before_or_during_run(self):
        tid = self._prep_trial_task()
        self.client.post(f"/api/tasks/{tid}/run", headers=self.h)
        cancel = self.client.post(f"/api/tasks/{tid}/cancel", headers=self.h)
        # 可能已结束 → 400；或取消成功 → 200
        self.assertIn(cancel.status_code, (200, 400), cancel.text)
        detail = {}
        for _ in range(40):
            detail = self.client.get(f"/api/tasks/{tid}", headers=self.h).json()
            if detail["status"] in {"cancelled", "success", "failed", "partial_failed"}:
                break
            time.sleep(0.1)
        self.assertIn(detail["status"], {"cancelled", "success", "failed", "partial_failed"})


if __name__ == "__main__":
    unittest.main()
