"""WP05：batch 绑定/分片守卫/幂等/预算 paused_budget/GC 保护。"""
from __future__ import annotations

import json
import time
import unittest
import uuid
from datetime import datetime, timedelta

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.database import async_session, init_db
from app.main import app
from app.models import BatchJob, BatchSnapshot
from app.services.batch_store import gc_expired_snapshots


class BatchBudgetApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def _dataset(self, n=3):
        ds = self.client.post("/api/datasets", json={"name": f"b-{int(time.time()*1000)}"}, headers=self.h).json()
        rows = [{"input": str(i), "reference": str(i)} for i in range(n)]
        self.client.post(
            f"/api/datasets/{ds['id']}/import",
            headers=self.h,
            files={"file": ("qa.json", json.dumps(rows).encode(), "application/json")},
        )
        return ds["id"]

    def test_wrong_snapshot_rejected(self):
        ds_id = self._dataset(2)
        run = self.client.post("/api/batch/run", json={"dataset_id": ds_id, "shard_size": 1}, headers=self.h)
        self.assertEqual(run.status_code, 200, run.text)
        bid = run.json()["batch_id"]
        bad = self.client.get(f"/api/batch/{bid}/shards/0", headers=self.h, params={"snapshot_id": "forged"})
        self.assertEqual(bad.status_code, 400, bad.text)

    def test_negative_and_oob_shard(self):
        ds_id = self._dataset(2)
        run = self.client.post("/api/batch/run", json={"dataset_id": ds_id, "shard_size": 1}, headers=self.h).json()
        bid = run["batch_id"]
        self.assertEqual(self.client.get(f"/api/batch/{bid}/shards/-1", headers=self.h).status_code, 400)
        self.assertEqual(self.client.get(f"/api/batch/{bid}/shards/99", headers=self.h).status_code, 400)

    def test_unknown_sample_rejected(self):
        ds_id = self._dataset(2)
        run = self.client.post("/api/batch/run", json={"dataset_id": ds_id, "shard_size": 1}, headers=self.h).json()
        bid = run["batch_id"]
        put = self.client.put(
            f"/api/batch/{bid}/shards/0/results",
            json={"results": [{"item_no": 999, "score": 1}], "tokens_used": 1},
            headers=self.h,
        )
        self.assertEqual(put.status_code, 400, put.text)

    def test_idempotent_same_hash(self):
        ds_id = self._dataset(2)
        run = self.client.post("/api/batch/run", json={"dataset_id": ds_id, "shard_size": 1}, headers=self.h).json()
        bid = run["batch_id"]
        shard = self.client.get(f"/api/batch/{bid}/shards/0", headers=self.h).json()
        item_no = shard["items"][0]["item_no"]
        body = {"results": [{"item_no": item_no, "score": 1}], "tokens_used": 2}
        r1 = self.client.put(f"/api/batch/{bid}/shards/0/results", json=body, headers=self.h)
        r2 = self.client.put(f"/api/batch/{bid}/shards/0/results", json=body, headers=self.h)
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertTrue(r2.json().get("idempotent"))

    def test_conflict_different_payload(self):
        ds_id = self._dataset(2)
        run = self.client.post("/api/batch/run", json={"dataset_id": ds_id, "shard_size": 1}, headers=self.h).json()
        bid = run["batch_id"]
        item_no = self.client.get(f"/api/batch/{bid}/shards/0", headers=self.h).json()["items"][0]["item_no"]
        self.client.put(
            f"/api/batch/{bid}/shards/0/results",
            json={"results": [{"item_no": item_no, "score": 1}], "tokens_used": 1},
            headers=self.h,
        )
        r2 = self.client.put(
            f"/api/batch/{bid}/shards/0/results",
            json={"results": [{"item_no": item_no, "score": 0}], "tokens_used": 1},
            headers=self.h,
        )
        self.assertEqual(r2.status_code, 409, r2.text)

    def test_budget_paused(self):
        ds_id = self._dataset(4)
        run = self.client.post(
            "/api/batch/run",
            json={"dataset_id": ds_id, "shard_size": 1, "token_budget": 3},
            headers=self.h,
        ).json()
        bid = run["batch_id"]
        # shard0 uses 2
        item0 = self.client.get(f"/api/batch/{bid}/shards/0", headers=self.h).json()["items"][0]["item_no"]
        r0 = self.client.put(
            f"/api/batch/{bid}/shards/0/results",
            json={"results": [{"item_no": item0, "score": 1}], "tokens_used": 2},
            headers=self.h,
        )
        self.assertEqual(r0.status_code, 200, r0.text)
        item1 = self.client.get(f"/api/batch/{bid}/shards/1", headers=self.h).json()["items"][0]["item_no"]
        r1 = self.client.put(
            f"/api/batch/{bid}/shards/1/results",
            json={"results": [{"item_no": item1, "score": 1}], "tokens_used": 2},
            headers=self.h,
        )
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertEqual(r1.json()["status"], "paused_budget")
        # further write rejected
        r2 = self.client.put(
            f"/api/batch/{bid}/shards/2/results",
            json={"results": [{"item_no": 99, "score": 1}], "tokens_used": 1},
            headers=self.h,
        )
        self.assertEqual(r2.status_code, 400, r2.text)


class BatchGcProtectTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()

    async def test_active_snapshot_not_gc(self):
        async with async_session() as db:
            sid = uuid.uuid4().hex[:16]
            snap = BatchSnapshot(
                snapshot_id=sid,
                dataset_id=1,
                version_id=1,
                checksum="x",
                item_count=1,
                file_path="",
                expires_at=datetime.utcnow() - timedelta(days=1),
            )
            db.add(snap)
            db.add(
                BatchJob(
                    batch_id=str(uuid.uuid4()),
                    snapshot_id=sid,
                    dataset_id=1,
                    status="running",
                    shard_size=1,
                    shard_count=1,
                )
            )
            await db.commit()
        async with async_session() as db:
            n = await gc_expired_snapshots(db)
            await db.commit()
            left = await db.scalar(select(BatchSnapshot).where(BatchSnapshot.snapshot_id == sid))
            self.assertIsNotNone(left)
            self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
