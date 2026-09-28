"""WP14 服务单结算与影子灰度。"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.main import app
from app.services.shadow_router import can_promote, evaluate_shadow
from app.services.service_billing import delivery_idem_key


class ShadowUnitTest(unittest.TestCase):
    def test_reject_client_score_and_return_production(self):
        r = evaluate_shadow(
            {"score": 0.9, "latency_ms": 100, "samples": [0.9, 0.91]},
            {"client_score": 0.99, "latency_ms": 100},
        )
        self.assertEqual(r["returned"], "production")
        self.assertFalse(next(g for g in r["gates"] if g["code"] == "client_score_rejected")["ok"])

    def test_drift_over_10_blocked(self):
        r = evaluate_shadow(
            {"score": 1.0, "latency_ms": 100, "samples": [1.0, 0.99]},
            {"score": 0.8, "latency_ms": 100, "samples": [0.8, 0.81]},
            traffic_pct=0.05,
        )
        self.assertFalse(r["promotable"])
        self.assertGreater(r["score_diff_rate"], 0.10)

    def test_constant_inconclusive(self):
        r = evaluate_shadow(
            {"score": 0.5, "samples": [0.5, 0.5, 0.5]},
            {"score": 0.5, "samples": [0.5, 0.5, 0.5]},
        )
        self.assertEqual(r["status"], "inconclusive")

    def test_candidate_failure_isolated(self):
        r = evaluate_shadow(
            {"score": 0.9, "latency_ms": 100, "samples": [0.9, 0.88]},
            {"score": 0.0, "failed": True, "samples": [0.0, 0.0]},
        )
        self.assertEqual(r["returned"], "production")
        self.assertFalse(r["promotable"])

    def test_promote_needs_7_days(self):
        shadow = evaluate_shadow(
            {"score": 0.9, "latency_ms": 100, "samples": [0.9, 0.91, 0.89]},
            {"score": 0.91, "latency_ms": 105, "samples": [0.91, 0.92, 0.90]},
            traffic_pct=0.05,
        )
        self.assertTrue(shadow["promotable"])
        ok, reason = can_promote(shadow, started_at=datetime.utcnow() - timedelta(days=2))
        self.assertFalse(ok)
        self.assertIn("evidence_window", reason)
        ok2, _ = can_promote(shadow, started_at=datetime.utcnow() - timedelta(days=8))
        self.assertTrue(ok2)


class ServiceApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        tok = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
        self.h = {"Authorization": f"Bearer {tok}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def _create_service(self):
        ws = self.client.get("/api/services/workspaces", headers=self.h).json()["items"][0]
        res = self.client.post(
            "/api/services",
            headers=self.h,
            json={
                "title": "wp14-svc",
                "industry": "general",
                "requirement": "need formal delivery",
                "workspace_id": ws["id"],
                "quote_mode": "auto",
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    def test_deliver_without_report_rejected(self):
        s = self._create_service()
        bad = self.client.post(
            f"/api/services/{s['id']}/status",
            headers=self.h,
            params={"status": "delivered"},
        )
        self.assertEqual(bad.status_code, 400, bad.text)

    def test_idempotent_delivery_settle(self):
        s = self._create_service()
        # 绑定伪报告路径：通过 status running 后手动 quote confirm，再写 report_path via deliver after setting path
        # 使用 shadow/promote 无关：直接 PATCH 不存在，改为先 quote 再在 DB 外用 render 不可用。
        # 通过 update status configuring 后，用 second request with report_summary AND set report via deliver after attaching task report.
        # 简化：调用服务内部 — 先把 report_path 用 quote detail 不行。
        # 用 SQLAlchemy 在测试中：通过 create + 直接调用 settle API path by setting report via status rejected then...
        # 实际：POST status delivered 前，先用 admin 接口没有 set report。改为用 client 创建后调用
        # `/status?status=running` then manually set report_path through a deliver that checks task.
        # 最稳：在测试中用 TestClient 无法直接改字段时，用 shadow 无关的 settle 单元。
        from app.database import async_session
        from app.models import EvalServiceRequest
        import asyncio
        from sqlalchemy import select

        async def _set_report(sid: int):
            async with async_session() as db:
                row = await db.get(EvalServiceRequest, sid)
                row.report_path = f"/tmp/service-{sid}.json"
                row.report_summary = "ok"
                await db.commit()

        asyncio.run(_set_report(s["id"]))
        d1 = self.client.post(f"/api/services/{s['id']}/status", headers=self.h, params={"status": "delivered"})
        self.assertEqual(d1.status_code, 200, d1.text)
        self.assertTrue(d1.json()["delivery_settled"])
        d2 = self.client.post(f"/api/services/{s['id']}/status", headers=self.h, params={"status": "delivered"})
        self.assertEqual(d2.status_code, 200, d2.text)
        self.assertTrue(d2.json()["delivery_settled"])
        self.assertEqual(delivery_idem_key(s["id"]), f"service-delivery:{s['id']}")

    def test_shadow_promote_rollback(self):
        s = self._create_service()
        sh = self.client.post(
            f"/api/services/{s['id']}/shadow",
            headers=self.h,
            json={
                "gray_version": "v-next",
                "traffic_pct": 0.05,
                "production": {"score": 0.9, "latency_ms": 100, "samples": [0.9, 0.91, 0.89]},
                "candidate": {"score": 0.91, "latency_ms": 102, "samples": [0.91, 0.92, 0.90]},
            },
        )
        self.assertEqual(sh.status_code, 200, sh.text)
        self.assertEqual(sh.json()["shadow"]["returned"], "production")
        # 证据不足 → 拒绝转正
        bad = self.client.post(f"/api/services/{s['id']}/promote", headers=self.h)
        self.assertEqual(bad.status_code, 400, bad.text)

        import asyncio
        from app.database import async_session
        from app.models import EvalServiceRequest

        async def _age(sid: int):
            async with async_session() as db:
                row = await db.get(EvalServiceRequest, sid)
                row.shadow_started_at = datetime.utcnow() - timedelta(days=8)
                await db.commit()

        asyncio.run(_age(s["id"]))
        ok = self.client.post(f"/api/services/{s['id']}/promote", headers=self.h)
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["production_version"], "v-next")
        self.assertEqual(ok.json()["previous_stable"], "v1")
        rb = self.client.post(f"/api/services/{s['id']}/rollback", headers=self.h)
        self.assertEqual(rb.status_code, 200, rb.text)
        self.assertEqual(rb.json()["production_version"], "v1")
        self.assertEqual(rb.json()["traffic_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
