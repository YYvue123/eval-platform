"""WP16 运维工单闭环、演练留痕、数据授权。"""
from __future__ import annotations

import unittest

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.main import app


class OpsGovernanceTest(unittest.TestCase):
    def _auth(self, client):
        login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(login.status_code, 200, login.text)
        token = login.json()["access_token"]
        me = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.status_code, 200, me.text)
        return {"Authorization": f"Bearer {token}"}, me.json()["id"]

    def test_ticket_requires_owner_and_resolution_to_close(self):
        with TestClient(app) as client:
            h, uid = self._auth(client)
            created = client.post(
                "/api/ops/tickets",
                headers=h,
                json={"title": "P0 ready fail", "category": "incident", "severity": "high"},
            )
            self.assertEqual(created.status_code, 200, created.text)
            tid = created.json()["id"]
            self.assertEqual(created.json()["status"], "open")
            self.assertIsNone(created.json()["owner_id"])

            bad = client.patch(
                f"/api/ops/tickets/{tid}",
                headers=h,
                json={"status": "closed", "resolution": "fixed"},
            )
            self.assertEqual(bad.status_code, 400, bad.text)

            bad2 = client.patch(
                f"/api/ops/tickets/{tid}",
                headers=h,
                json={"status": "closed", "owner_id": uid},
            )
            self.assertEqual(bad2.status_code, 400, bad2.text)

            ok = client.patch(
                f"/api/ops/tickets/{tid}",
                headers=h,
                json={"status": "closed", "owner_id": uid, "resolution": "rolled back per runbook"},
            )
            self.assertEqual(ok.status_code, 200, ok.text)
            self.assertEqual(ok.json()["status"], "closed")
            self.assertEqual(ok.json()["owner_id"], uid)
            self.assertTrue(ok.json()["closed_at"])

            disabled = client.patch(
                f"/api/ops/tickets/{tid}",
                headers=h,
                json={"status": "disabled"},
            )
            # already closed — update_ticket allows disabled from closed? status closed then disabled
            # Our code: if ticket.status == "disabled" only blocks. closed can go to disabled.
            self.assertEqual(disabled.status_code, 200, disabled.text)
            self.assertEqual(disabled.json()["status"], "disabled")

            # history still listable
            listed = client.get("/api/ops/tickets", headers=h)
            self.assertEqual(listed.status_code, 200)
            ids = [x["id"] for x in listed.json()["items"]]
            self.assertIn(tid, ids)

    def test_authorization_traceable_and_disable_keeps_row(self):
        with TestClient(app) as client:
            h, _ = self._auth(client)
            miss = client.post(
                "/api/ops/authorizations",
                headers=h,
                json={"asset_ref": "ds-1", "license_spdx": "", "grantor": "OrgA"},
            )
            self.assertEqual(miss.status_code, 400)

            a = client.post(
                "/api/ops/authorizations",
                headers=h,
                json={
                    "asset_ref": "bench.text.chat",
                    "license_spdx": "LicenseRef-Internal",
                    "grantor": "DataOwner",
                    "purpose": "pilot eval",
                    "evidence_uri": "docs/licenses/THIRD_PARTY.md",
                },
            )
            self.assertEqual(a.status_code, 200, a.text)
            aid = a.json()["id"]
            dis = client.post(f"/api/ops/authorizations/{aid}/disable", headers=h)
            self.assertEqual(dis.status_code, 200)
            self.assertTrue(dis.json()["disabled"])
            all_rows = client.get("/api/ops/authorizations", headers=h, params={"include_disabled": True})
            self.assertTrue(any(x["id"] == aid for x in all_rows.json()["items"]))

    def test_drill_and_report_and_policy(self):
        with TestClient(app) as client:
            h, _ = self._auth(client)
            d = client.post(
                "/api/ops/drills",
                headers=h,
                json={
                    "drill_type": "rollback",
                    "result": "pass",
                    "checklist": ["backup", "switch-upstream", "ready"],
                    "notes": "AC46",
                    "evidence": {"runbook": "docs/operations/WP15-runbook.md"},
                },
            )
            self.assertEqual(d.status_code, 200, d.text)
            self.assertEqual(d.json()["policy_version"], "2026-09-28-wp16")

            report = client.get("/api/ops/report", headers=h)
            self.assertEqual(report.status_code, 200, report.text)
            body = report.json()
            self.assertGreaterEqual(body["drills"]["total"], 1)
            self.assertTrue(body["benchmark_ecosystem"]["documented"])

            policy = client.get("/api/ops/policy", headers=h)
            self.assertEqual(policy.status_code, 200)
            paths = [x["path"] for x in policy.json()["docs"]]
            self.assertIn("docs/operations/benchmark-ecosystem.md", paths)
            self.assertIn("CONTRIBUTING.md", paths)


if __name__ == "__main__":
    unittest.main()
