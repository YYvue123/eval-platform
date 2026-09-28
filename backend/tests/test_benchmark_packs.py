"""WP11b–f：金标包、媒体适配、MUT oracle、行业包、模拟器。"""
from __future__ import annotations

import unittest

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.main import app
from app.services import benchmark_packs as packs
from app.services import media_adapter
from app.services import mut_oracle
from app.services import scenario_simulators as sims
from app.services.benchmark_registry import compute_readiness, default_suites


class PackUnitTest(unittest.TestCase):
    def test_text_five_packs_load(self):
        for code in ("bench.chat", "bench.table", "bench.writing", "bench.rag", "bench.code"):
            summary = packs.pack_summary(code)
            self.assertGreaterEqual(summary["sample_count"], 3)
            self.assertTrue(summary["calibration_ok"])
            self.assertFalse(packs.assert_pack_ready_resources(code))

    def test_industry_finance_gov(self):
        for code in ("bench.finance", "bench.gov"):
            self.assertFalse(packs.assert_pack_ready_resources(code))
            suite = next(s for s in default_suites() if s["code"] == code)
            self.assertEqual(compute_readiness(suite)["status"], "ready")

    def test_media_fixture_not_string(self):
        pack = packs.load_pack("bench.media.video")
        for s in pack["samples"]:
            errs = media_adapter.validate_media_sample(s)
            self.assertFalse(errs, errs)
        bad = media_adapter.validate_media_sample({"media": "fake description of a video"})
        self.assertIn("media_must_not_be_string_description", bad)

    def test_code_sandbox_no_host_exec(self):
        sample = packs.load_pack("bench.code")["samples"][0]
        ok = sims.code_sandbox_score(sample)
        self.assertFalse(ok["host_executed"])
        self.assertEqual(ok["status"], "ok")
        sample_bad = {**sample, "execute_on_host": True}
        with self.assertRaises(sims.HostExecutionForbidden):
            sims.code_sandbox_score(sample_bad)

    def test_table_simulator(self):
        sample = packs.load_pack("bench.table")["samples"][0]
        r = sims.table_calc(sample)
        self.assertTrue(r["ok"], r)

    def test_mut_oracle_and_forbidden_tool(self):
        pack = packs.load_pack("bench.mut.episode")
        gold = mut_oracle.run_episode(pack["samples"][0])
        self.assertTrue(gold["oracle"]["ok"])
        probe = mut_oracle.run_episode(pack["samples"][2])
        self.assertTrue(any(d.startswith("denied:") for d in probe["tool_denials"]))
        self.assertEqual(probe["trajectory_metric_status"], "not_observable")
        # 独立最终状态：错误状态应失败
        bad = mut_oracle.verify_final_state({"total": 20}, {"total": 19})
        self.assertFalse(bad["ok"])


class PackApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        tok = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
        self.h = {"Authorization": f"Bearer {tok}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_packs_and_simulate(self):
        res = self.client.get("/api/benchmarks/packs", headers=self.h)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertGreaterEqual(res.json()["total"], 9)

        sim = self.client.post(
            "/api/benchmarks/simulate",
            json={"simulator": "sim.table_calc", "suite_code": "bench.table", "sample_id": "table-001"},
            headers=self.h,
        )
        self.assertEqual(sim.status_code, 200, sim.text)
        self.assertTrue(sim.json()["ok"])

        media = self.client.post(
            "/api/benchmarks/simulate",
            json={"simulator": "sim.media_probe", "suite_code": "bench.media.video"},
            headers=self.h,
        )
        self.assertEqual(media.status_code, 200, media.text)
        self.assertTrue(media.json()["ok"])

        mut = self.client.post(
            "/api/benchmarks/simulate",
            json={"simulator": "sim.mut_episode", "suite_code": "bench.mut.episode", "sample_id": "mut-003"},
            headers=self.h,
        )
        self.assertEqual(mut.status_code, 200, mut.text)
        self.assertTrue(mut.json()["oracle"]["ok"])

    def test_ready_suites_listed(self):
        res = self.client.get("/api/benchmarks", headers=self.h, params={"readiness": "ready"})
        self.assertEqual(res.status_code, 200)
        codes = {i["code"] for i in res.json()["items"]}
        for c in ("bench.chat", "bench.finance", "bench.gov", "bench.media.video", "bench.mut.episode"):
            self.assertIn(c, codes, codes)


if __name__ == "__main__":
    unittest.main()
