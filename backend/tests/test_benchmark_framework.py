"""WP11a 基准框架：readiness、MUT 工具隔离、媒体字符串拒绝。"""
from __future__ import annotations

import unittest

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.main import app
from app.services.benchmark_registry import (
    PLATFORM_ADMIN_TOOLS,
    assert_mut_tool_allowed,
    compute_readiness,
    default_suites,
    validate_sample_against_schema,
)


class RegistryUnitTest(unittest.TestCase):
    def test_text_suite_can_be_ready(self):
        suite = next(s for s in default_suites() if s["code"] == "bench.chat")
        r = compute_readiness(suite)
        self.assertEqual(r["status"], "ready", r)
        self.assertFalse(r["blockers"], r)

    def test_finance_pack_ready(self):
        suite = next(s for s in default_suites() if s["code"] == "bench.finance")
        r = compute_readiness(suite)
        self.assertEqual(r["status"], "ready", r)

    def test_healthcare_skeleton_not_ready(self):
        suite = next(s for s in default_suites() if s["code"] == "bench.healthcare")
        r = compute_readiness(suite)
        self.assertIn(r["status"], {"draft", "blocked"})
        self.assertIn("missing_real_inputs", r["blockers"])

    def test_media_string_sample_rejected(self):
        errs = validate_sample_against_schema("media", {"media": "a cat video description"})
        self.assertTrue(errs)

    def test_media_suite_ready_with_fixtures(self):
        suite = next(s for s in default_suites() if s["code"] == "bench.media.video")
        r = compute_readiness(suite)
        self.assertEqual(r["status"], "ready", r)

    def test_mut_forbids_platform_tools(self):
        for t in ("create_task", "publish_dataset", "promote_service"):
            self.assertIn(t, PLATFORM_ADMIN_TOOLS)
            with self.assertRaises(PermissionError):
                assert_mut_tool_allowed(t)

    def test_validate_media_sample(self):
        errs = validate_sample_against_schema("media", {"media": "a cat video description"})
        self.assertTrue(errs)
        ok = validate_sample_against_schema(
            "media",
            {"media_uri": "s3://bucket/a.mp4", "media_type": "video"},
        )
        self.assertFalse(ok)

    def test_code_host_exec_rejected(self):
        errs = validate_sample_against_schema("code", {"prompt": "write sort", "execute_on_host": True})
        self.assertIn("code_must_not_execute_on_host", errs)

    def test_not_observable_metric_flagged(self):
        suite = next(s for s in default_suites() if s["code"] == "bench.mut.episode")
        r = compute_readiness(suite)
        self.assertEqual(r["status"], "ready", r)
        self.assertTrue(any(w.startswith("not_observable:") for w in r["warnings"]))


class BenchmarkApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        tok = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
        self.h = {"Authorization": f"Bearer {tok}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_list_and_metrics(self):
        res = self.client.get("/api/benchmarks", headers=self.h)
        self.assertEqual(res.status_code, 200, res.text)
        items = res.json()["items"]
        self.assertGreaterEqual(len(items), 5)
        codes = {i["code"] for i in items}
        self.assertIn("bench.chat", codes)
        metrics = self.client.get("/api/benchmarks/metrics", headers=self.h)
        self.assertEqual(metrics.status_code, 200)
        self.assertGreaterEqual(metrics.json()["total"], 5)

    def test_mut_check_tool_forbidden(self):
        bad = self.client.post("/api/benchmarks/mut/check-tool", json={"tool_name": "create_task"}, headers=self.h)
        self.assertEqual(bad.status_code, 403, bad.text)

    def test_mark_ready_blocked_when_gaps(self):
        bad = self.client.post("/api/benchmarks/bench.healthcare/mark-ready", json={"force": False}, headers=self.h)
        self.assertEqual(bad.status_code, 400, bad.text)
        forced = self.client.post("/api/benchmarks/bench.healthcare/mark-ready", json={"force": True}, headers=self.h)
        self.assertEqual(forced.status_code, 400, forced.text)

    def test_validate_sample_api(self):
        res = self.client.post(
            "/api/benchmarks/validate-sample",
            json={"modality": "media", "sample": {"media_as_string": True}},
            headers=self.h,
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["ok"])


if __name__ == "__main__":
    unittest.main()
