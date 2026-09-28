"""WP10 质量增强与提示词实验。"""
from __future__ import annotations

import json
import time
import unittest
import uuid

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.main import app
from app.services.quality_checker import check_items
from app.services.prompt_experiment import paired_stats, split_develop_holdout


class QualityRulesUnitTest(unittest.TestCase):
    def test_near_duplicate_and_consistency_explainable(self):
        items = [
            {"id": 1, "item_no": 1, "input_content": "什么是首都", "reference_answer": "北京"},
            {"id": 2, "item_no": 2, "input_content": "什么是首都啊", "reference_answer": "北京"},
            {"id": 3, "item_no": 3, "input_content": "x", "reference_answer": "a" * 200},
            {"id": 4, "item_no": 4, "input_content": "有输入无参考", "reference_answer": ""},
        ]
        res = check_items(items)
        self.assertTrue(res.get("explainable"))
        self.assertIn("near_duplicate", res["rules_applied"])
        self.assertIn("consistency_pair", res["rules_applied"])
        codes = {r["rule_code"] for r in res["issue_records"]}
        self.assertTrue(codes & {"near_duplicate", "consistency_pair", "human_accuracy_review", "completeness_reference"})


class SplitHoldoutUnitTest(unittest.TestCase):
    def test_holdout_not_overlap_develop(self):
        ids = list(range(1, 21))
        d, h = split_develop_holdout(ids, 0.3)
        self.assertTrue(d and h)
        self.assertEqual(set(d) & set(h), set())
        self.assertEqual(set(d) | set(h), set(ids))

    def test_paired_stats_recomputable(self):
        pairs = [
            {"item_id": 1, "baseline": "a", "candidate": "a", "reference": "a"},
            {"item_id": 2, "baseline": "x", "candidate": "b", "reference": "b"},
        ]
        s1 = paired_stats(pairs)
        s2 = paired_stats(pairs)
        self.assertEqual(s1, s2)
        self.assertEqual(s1["avg_diff"], s1["avg_candidate"] - s1["avg_baseline"])


class QualityFixRecheckApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        tok = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
        self.h = {"Authorization": f"Bearer {tok}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_fix_creates_version_and_rechecks(self):
        ds = self.client.post("/api/datasets", json={"name": f"q10-{uuid.uuid4().hex[:6]}"}, headers=self.h).json()
        payload = json.dumps([
            {"input": "", "reference": "x"},
            {"input": "hello", "reference": "world"},
        ]).encode()
        self.client.post(f"/api/datasets/{ds['id']}/import", headers=self.h, files={"file": ("qa.json", payload, "application/json")})
        run = self.client.post("/api/quality/run", params={"dataset_id": ds["id"]}, headers=self.h)
        self.assertEqual(run.status_code, 200, run.text)
        issues = self.client.get("/api/quality/issues", params={"dataset_id": ds["id"]}, headers=self.h)
        self.assertEqual(issues.status_code, 200, issues.text)
        open_issues = [i for i in issues.json()["items"] if i["status"] == "open"]
        self.assertTrue(open_issues)
        issue = open_issues[0]
        before_ver = self.client.get(f"/api/datasets/{ds['id']}", headers=self.h).json().get("current_version_id")
        fix = self.client.post(
            f"/api/quality/issues/{issue['id']}/handle",
            json={"action": "fix", "input_content": "补全后的输入", "reference_answer": "x", "recheck": True, "note": "wp10"},
            headers=self.h,
        )
        self.assertEqual(fix.status_code, 200, fix.text)
        body = fix.json()
        self.assertEqual(body["issue"]["status"], "fixed")
        self.assertIn("recheck", body)
        after = self.client.get(f"/api/datasets/{ds['id']}", headers=self.h).json()
        self.assertNotEqual(after.get("current_version_id"), before_ver)


class PromptExperimentApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        tok = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
        self.h = {"Authorization": f"Bearer {tok}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_experiment_holdout_gate(self):
        ds = self.client.post("/api/datasets", json={"name": f"pe-{uuid.uuid4().hex[:6]}"}, headers=self.h).json()
        rows = [{"input": f"q{i}", "reference": f"a{i}"} for i in range(10)]
        self.client.post(
            f"/api/datasets/{ds['id']}/import",
            headers=self.h,
            files={"file": ("qa.json", json.dumps(rows).encode(), "application/json")},
        )
        pr = self.client.post(
            "/api/prompts",
            json={"name": f"p-{int(time.time())}", "prompt_content": "回答：{{input}}", "applicable_task": "qa"},
            headers=self.h,
        )
        self.assertEqual(pr.status_code, 200, pr.text)
        pid = pr.json()["id"]
        exp = self.client.post(
            f"/api/prompts/{pid}/experiments",
            json={"dataset_id": ds["id"], "holdout_ratio": 0.3, "token_budget": 5000},
            headers=self.h,
        )
        self.assertEqual(exp.status_code, 200, exp.text)
        data = exp.json()
        self.assertTrue(data["develop_ids"])
        self.assertTrue(data["holdout_ids"])
        self.assertEqual(set(data["develop_ids"]) & set(data["holdout_ids"]), set())
        self.assertIn("avg_diff", data["pair_stats"])

        pub = self.client.post(
            f"/api/prompts/{pid}/experiments/{data['id']}/publish",
            json={"force": False},
            headers=self.h,
        )
        self.assertEqual(pub.status_code, 200, pub.text)
        # 无显著收益时不应自动发布
        if not data["publish_recommended"]:
            self.assertFalse(pub.json().get("published"))
            self.assertEqual(pub.json().get("reason"), "no_significant_gain")


if __name__ == "__main__":
    unittest.main()
