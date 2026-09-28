"""WP15 生产加固：探针、准入、恢复演练、默认凭证门禁。"""
from __future__ import annotations

import unittest

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.backup import restore_drill
from app.services.degrade import clear_degrade, set_degrade
from app.services.prod_guards import (
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_SECRET_KEY,
    assert_production_safe,
    bootstrap_admin_password,
)


class ProdGuardsUnitTest(unittest.TestCase):
    def test_production_rejects_default_secret(self):
        old_env, old_key = settings.APP_ENV, settings.SECRET_KEY
        try:
            settings.APP_ENV = "production"
            settings.SECRET_KEY = DEFAULT_SECRET_KEY
            with self.assertRaises(RuntimeError):
                assert_production_safe()
            settings.SECRET_KEY = "x" * 32
            assert_production_safe()  # no raise
        finally:
            settings.APP_ENV = old_env
            settings.SECRET_KEY = old_key

    def test_production_bootstrap_rejects_admin123(self):
        import os

        old_env = settings.APP_ENV
        old = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
        try:
            settings.APP_ENV = "production"
            os.environ["ADMIN_BOOTSTRAP_PASSWORD"] = DEFAULT_ADMIN_PASSWORD
            with self.assertRaises(RuntimeError):
                bootstrap_admin_password()
            os.environ["ADMIN_BOOTSTRAP_PASSWORD"] = "ProdOnly!Passw0rd"
            self.assertEqual(bootstrap_admin_password(), "ProdOnly!Passw0rd")
        finally:
            settings.APP_ENV = old_env
            if old is None:
                os.environ.pop("ADMIN_BOOTSTRAP_PASSWORD", None)
            else:
                os.environ["ADMIN_BOOTSTRAP_PASSWORD"] = old


class LiveReadyTest(unittest.TestCase):
    def tearDown(self):
        clear_degrade()

    def test_live_always_ok(self):
        with TestClient(app) as client:
            r = client.get("/api/live")
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()["ok"])

    def test_ready_503_when_db_degraded(self):
        with TestClient(app) as client:
            ok = client.get("/api/ready")
            self.assertEqual(ok.status_code, 200, ok.text)
            set_degrade(db_unavailable=True, reason="unit-test")
            bad = client.get("/api/ready")
            self.assertEqual(bad.status_code, 503)
            self.assertFalse(bad.json()["ok"])
            clear_degrade()
            again = client.get("/api/ready")
            self.assertEqual(again.status_code, 200)

    def test_health_503_when_cert_expired_flag(self):
        with TestClient(app) as client:
            set_degrade(cert_expired=True, reason="cert-drill")
            r = client.get("/api/health")
            self.assertEqual(r.status_code, 503)
            self.assertFalse(r.json()["ok"])


class AdmissionAndRestoreTest(unittest.TestCase):
    def setUp(self):
        clear_degrade()

    def tearDown(self):
        clear_degrade()

    def _auth(self, client):
        login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(login.status_code, 200, login.text)
        return {"Authorization": f"Bearer {login.json()['access_token']}"}

    def test_admission_run_basic_and_full(self):
        with TestClient(app) as client:
            h = self._auth(client)
            basic = client.post("/api/ops/admission/run", headers=h, json={"level": "basic"})
            self.assertEqual(basic.status_code, 200, basic.text)
            body = basic.json()
            self.assertIn(body["ok"], (True, False, None))
            self.assertTrue(body["artifact_hash"])
            by = {x["code"]: x for x in body["items"]}
            self.assertEqual(by["manifest"]["status"], "unknown")
            self.assertIsNone(by["manifest"]["ok"])
            self.assertEqual(by["errors"]["status"], "unknown")
            self.assertEqual(by["connectivity"]["status"], "measured")
            self.assertEqual(by["illegal_input"]["status"], "measured")
            self.assertTrue(by["illegal_input"]["ok"])

            full = client.post("/api/ops/admission/run", headers=h, json={"level": "full"})
            self.assertEqual(full.status_code, 200, full.text)
            fbody = full.json()
            fby = {x["code"]: x for x in fbody["items"]}
            self.assertIn("stress", fby)
            self.assertEqual(fby["external_security"]["status"], "unknown")
            # 完整级含 unknown → overall 不得为 True
            self.assertIsNone(fbody["ok"])

            latest = client.get("/api/ops/admission/latest", headers=h)
            self.assertEqual(latest.status_code, 200)
            self.assertEqual(latest.json()["id"], fbody["id"])

    def test_restore_drill_measures_rpo_rto(self):
        with TestClient(app) as client:
            h = self._auth(client)
            bak = client.post("/api/ops/backup", headers=h)
            self.assertEqual(bak.status_code, 200, bak.text)
            drill = client.post("/api/ops/restore-drill", headers=h)
            self.assertEqual(drill.status_code, 200, drill.text)
            d = drill.json()
            self.assertTrue(d["ok"])
            self.assertTrue(d["hash_match"])
            self.assertIn("rpo_seconds", d)
            self.assertIn("rto_seconds", d)
            self.assertGreaterEqual(d["rto_seconds"], 0)
            # 直接服务层再验一次
            again = restore_drill(backup_path=bak.json()["path"])
            self.assertTrue(again["hash_match"])

    def test_fault_injection_roundtrip(self):
        with TestClient(app) as client:
            h = self._auth(client)
            inj = client.post(
                "/api/ops/fault",
                headers=h,
                json={"db_unavailable": True, "reason": "ac44"},
            )
            self.assertEqual(inj.status_code, 200)
            self.assertTrue(inj.json()["degrade"]["db_unavailable"])
            self.assertEqual(client.get("/api/ready").status_code, 503)
            clr = client.post("/api/ops/fault", headers=h, json={"clear": True})
            self.assertEqual(clr.status_code, 200)
            self.assertEqual(client.get("/api/ready").status_code, 200)


if __name__ == "__main__":
    unittest.main()
