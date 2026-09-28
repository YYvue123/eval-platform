"""WP14 / U0 F02：影子仅服务端观测，拒绝客户端分数。"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.main import app
from app.services.shadow_router import can_promote, evaluate_shadow, make_server_observation
from app.services.service_billing import delivery_idem_key


def _obs(score: float, samples: list[float], *, failed: bool = False, oid: str = "o1"):
    return make_server_observation(
        observation_id=oid,
        score=score,
        latency_ms=100.0,
        samples=samples,
        failed=failed,
    )


class ShadowUnitTest(unittest.TestCase):
    def test_reject_client_score(self):
        r = evaluate_shadow(
            {"score": 0.9, "latency_ms": 100, "samples": [0.9, 0.91]},
            {"client_score": 0.99, "latency_ms": 100},
        )
        self.assertEqual(r["returned"], "production")
        self.assertEqual(r["status"], "rejected")
        self.assertFalse(next(g for g in r["gates"] if g["code"] == "client_observation_rejected")["ok"])

    def test_empty_observation_insufficient(self):
        r = evaluate_shadow({}, {})
        self.assertEqual(r["status"], "insufficient_evidence")
        self.assertFalse(r["promotable"])

    def test_drift_over_10_blocked(self):
        r = evaluate_shadow(
            _obs(1.0, [1.0, 0.99], oid="p"),
            _obs(0.8, [0.8, 0.81], oid="c"),
            traffic_pct=0.05,
            evidence_pair_count=2,
            started_at=datetime.utcnow() - timedelta(days=8),
        )
        self.assertFalse(r["promotable"])
        self.assertGreater(r["score_diff_rate"], 0.10)

    def test_constant_inconclusive(self):
        r = evaluate_shadow(
            _obs(0.5, [0.5, 0.5, 0.5], oid="p"),
            _obs(0.5, [0.5, 0.5, 0.5], oid="c"),
            evidence_pair_count=2,
            started_at=datetime.utcnow() - timedelta(days=8),
        )
        self.assertEqual(r["status"], "inconclusive")

    def test_candidate_failure_isolated(self):
        r = evaluate_shadow(
            _obs(0.9, [0.9, 0.88], oid="p"),
            _obs(0.0, [0.0, 0.1], oid="c", failed=True),
            evidence_pair_count=2,
            started_at=datetime.utcnow() - timedelta(days=8),
        )
        self.assertEqual(r["returned"], "production")
        self.assertFalse(r["promotable"])

    def test_promote_needs_7_days_and_pairs(self):
        shadow = evaluate_shadow(
            _obs(0.9, [0.9, 0.91, 0.89], oid="p"),
            _obs(0.91, [0.91, 0.92, 0.90], oid="c"),
            traffic_pct=0.05,
            evidence_pair_count=2,
            started_at=datetime.utcnow() - timedelta(days=8),
        )
        self.assertTrue(shadow["promotable"])
        ok, reason = can_promote(shadow, started_at=datetime.utcnow() - timedelta(days=2))
        self.assertFalse(ok)
        self.assertIn("evidence_window", reason)
        ok2, _ = can_promote(shadow, started_at=datetime.utcnow() - timedelta(days=8))
        self.assertTrue(ok2)
        bad_pairs = {**shadow, "evidence_pair_count": 1}
        ok3, reason3 = can_promote(bad_pairs, started_at=datetime.utcnow() - timedelta(days=8))
        self.assertFalse(ok3)
        self.assertIn("pairs", reason3)


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
        from app.database import async_session
        from app.models import EvalServiceRequest
        import asyncio

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

    def test_shadow_rejects_client_scores_and_blocks_promote(self):
        s = self._create_service()
        # 请求体即便带分数也会被忽略；无绑定模型 → insufficient
        sh = self.client.post(
            f"/api/services/{s['id']}/shadow",
            headers=self.h,
            json={
                "gray_version": "v-next",
                "traffic_pct": 0.05,
                "production": {"score": 0.9, "samples": [0.9, 0.91]},
                "candidate": {"score": 0.99, "samples": [0.99, 0.98]},
            },
        )
        self.assertEqual(sh.status_code, 200, sh.text)
        shadow = sh.json()["shadow"]
        self.assertEqual(shadow["returned"], "production")
        self.assertIn(shadow.get("status"), {"insufficient_evidence", "rejected", "blocked", "inconclusive"})
        self.assertFalse(shadow.get("promotable"))
        bad = self.client.post(f"/api/services/{s['id']}/promote", headers=self.h)
        self.assertEqual(bad.status_code, 400, bad.text)

        # 即使回填时间窗，无服务端成对观测仍不可转正
        import asyncio
        from app.database import async_session
        from app.models import EvalServiceRequest

        async def _age(sid: int):
            async with async_session() as db:
                row = await db.get(EvalServiceRequest, sid)
                row.shadow_started_at = datetime.utcnow() - timedelta(days=8)
                await db.commit()

        asyncio.run(_age(s["id"]))
        still = self.client.post(f"/api/services/{s['id']}/promote", headers=self.h)
        self.assertEqual(still.status_code, 400, still.text)

    def test_shadow_promote_with_server_evidence(self):
        s = self._create_service()
        import asyncio
        from app.database import async_session
        from app.models import EvalServiceRequest
        from app.utils.jsonutil import dumps

        async def _inject(sid: int):
            async with async_session() as db:
                row = await db.get(EvalServiceRequest, sid)
                row.shadow_started_at = datetime.utcnow() - timedelta(days=8)
                row.gray_version = "v-next"
                ev = evaluate_shadow(
                    _obs(0.9, [0.9, 0.91, 0.89], oid="sp"),
                    _obs(0.91, [0.91, 0.92, 0.90], oid="sc"),
                    traffic_pct=0.05,
                    evidence_pair_count=2,
                    started_at=row.shadow_started_at,
                )
                row.shadow_json = dumps(ev)
                await db.commit()

        asyncio.run(_inject(s["id"]))
        ok = self.client.post(f"/api/services/{s['id']}/promote", headers=self.h)
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["production_version"], "v-next")
        rb = self.client.post(f"/api/services/{s['id']}/rollback", headers=self.h)
        self.assertEqual(rb.status_code, 200, rb.text)
        self.assertEqual(rb.json()["production_version"], "v1")


if __name__ == "__main__":
    unittest.main()
