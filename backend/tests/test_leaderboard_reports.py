"""WP13 可比榜单与证据报告。"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.main import app
from app.services.leaderboard import (
    cohort_id_of,
    freeze_normalize,
    is_formal_eligible,
    rank_with_ties,
    recalculate_cost,
)
from app.services.report_archive import write_task_report, report_formats_status


class LeaderboardUnitTest(unittest.TestCase):
    def test_exclude_trial_simulation(self):
        t = MagicMock(trial_run=True, simulation=False, status="success")
        ok, reason = is_formal_eligible(t)
        self.assertFalse(ok)
        self.assertEqual(reason, "trial_run")
        t2 = MagicMock(trial_run=False, simulation=True, status="success")
        self.assertFalse(is_formal_eligible(t2)[0])

    def test_freeze_normalize_keeps_null(self):
        out = freeze_normalize([0.2, None, 0.8], 0.0, 1.0)
        self.assertEqual(out[0], 0.2)
        self.assertIsNone(out[1])
        self.assertEqual(out[2], 0.8)

    def test_rank_ties(self):
        items = [
            {"norm_score": 0.9, "pass_rate": 1},
            {"norm_score": 0.9, "pass_rate": 0.8},
            {"norm_score": 0.5, "pass_rate": 1},
            {"norm_score": None, "pass_rate": 0},
        ]
        ranked = rank_with_ties(items)
        self.assertEqual(ranked[0]["rank"], 1)
        self.assertEqual(ranked[1]["rank"], 1)
        self.assertTrue(ranked[1]["tied"])
        self.assertEqual(ranked[2]["rank"], 3)
        self.assertIsNone(ranked[3]["rank"])

    def test_cohort_differs_by_judge(self):
        a = MagicMock(dataset_version_id=1, dataset_id=1, judge_resource_id="builtin/exact_match", tool_version="1", metric_weights_json="{}", scene="chat")
        b = MagicMock(dataset_version_id=1, dataset_id=1, judge_resource_id="builtin/fuzzy", tool_version="1", metric_weights_json="{}", scene="chat")
        self.assertNotEqual(cohort_id_of(a), cohort_id_of(b))

    def test_cost_recomputable(self):
        task = MagicMock(tokens_used=1000, total=10)
        cost = MagicMock(token_price_per_1k=1.0, latency_price_per_sec=0.0, gpu_hour_price=0.0)
        bill = recalculate_cost(task, cost)
        self.assertEqual(bill["total_cost"], 1.0)


class ReportUnitTest(unittest.TestCase):
    def test_report_has_evidence_and_format_status(self):
        from types import SimpleNamespace
        task = SimpleNamespace(
            id=90001,
            name="wp13-report",
            status="success",
            scene="chat",
            industry="general",
            template_code="",
            dataset_id=1,
            dataset_version_id=1,
            model_id=1,
            model_version_id=None,
            prompt_id=None,
            prompt_version_id=None,
            judge_resource_id="builtin/exact_match",
            tool_version="1",
            snapshot_id="",
            batch_id="",
            total=2,
            success_count=2,
            fail_count=0,
            avg_score=0.9,
            pass_rate=1.0,
            report_summary="ok",
            tokens_used=10,
        )
        path = write_task_report(task, {"results": [{"id": 1, "item_no": 1, "score": 1.0, "passed": True}]})
        self.assertTrue(path.endswith("task-90001.json"))
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("evidence_id", text)
        self.assertIn("ev-90001-summary", text)
        st = report_formats_status(90001)
        self.assertEqual(st["formats"]["json"]["status"], "ready")
        self.assertEqual(st["formats"]["pdf"]["status"], "ready")


class LeaderboardApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        tok = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
        self.h = {"Authorization": f"Bearer {tok}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_board_and_publish_rollback(self):
        res = self.client.get("/api/leaderboard", headers=self.h, params={"board": "overall"})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertIn("excluded", body)
        self.assertIn("cohort_id", body)

        pub = self.client.post("/api/leaderboard/releases/publish", headers=self.h, params={"board": "overall"}, json={"note": "wp13"})
        self.assertEqual(pub.status_code, 200, pub.text)
        rid = pub.json()["id"]
        self.assertTrue(pub.json()["is_current"])

        # 再发一版再回滚
        pub2 = self.client.post("/api/leaderboard/releases/publish", headers=self.h, params={"board": "overall"}, json={"note": "v2"})
        self.assertEqual(pub2.status_code, 200, pub2.text)
        rb = self.client.post("/api/leaderboard/releases/rollback", headers=self.h, params={"board": "overall"})
        self.assertEqual(rb.status_code, 200, rb.text)
        self.assertEqual(rb.json()["id"], rid)
        self.assertTrue(rb.json()["is_current"])

    def test_report_status_endpoint(self):
        # 任意存在任务
        tasks = self.client.get("/api/tasks", headers=self.h, params={"page_size": 1})
        self.assertEqual(tasks.status_code, 200)
        items = tasks.json().get("items") or []
        if not items:
            self.skipTest("no tasks")
        tid = items[0]["id"]
        st = self.client.get(f"/api/tasks/{tid}/report-status", headers=self.h)
        self.assertEqual(st.status_code, 200, st.text)
        self.assertIn("formats", st.json())


if __name__ == "__main__":
    unittest.main()
