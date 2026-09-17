import json
import time
import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.services.builtin_tools import run_builtin_tool
from app.services.dataset_parser import parse_bytes
from app.services.protocol import validate_manifest
from app.services.quality_checker import check_items
from app.services.builtin_manifests import BUILTIN_MANIFESTS


class EvalFlowTest(unittest.TestCase):
    def test_parser_and_quality(self):
        rows = parse_bytes("qa.json", json.dumps([
            {"input": "1+1", "reference": "2"},
            {"question": "首都", "answer": "北京"},
        ]).encode())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["input_content"], "1+1")
        report = check_items(rows)
        self.assertEqual(report["status"], "passed")

    def test_builtin_judge(self):
        self.assertTrue(run_builtin_tool("builtin/exact_match", {"prediction": "北京", "reference": "北京"})["passed"])
        self.assertFalse(run_builtin_tool("builtin/exact_match", {"prediction": "上海", "reference": "北京"})["passed"])

    def test_manifests_valid(self):
        for mf in BUILTIN_MANIFESTS:
            self.assertEqual(validate_manifest(mf), [])

    def test_end_to_end_eval(self):
        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            self.assertEqual(login.status_code, 200)
            token = login.json()["access_token"]
            h = {"Authorization": f"Bearer {token}"}

            ds = client.post("/api/datasets", json={"name": f"smoke-{int(time.time())}", "task_type": "qa"}, headers=h)
            self.assertEqual(ds.status_code, 200, ds.text)
            ds_id = ds.json()["id"]
            payload = json.dumps([
                {"input": "中国首都", "reference": "北京"},
                {"input": "1+1", "reference": "2"},
            ]).encode()
            imp = client.post(
                f"/api/datasets/{ds_id}/import",
                headers=h,
                files={"file": ("qa.json", payload, "application/json")},
            )
            self.assertEqual(imp.status_code, 200, imp.text)
            self.assertEqual(imp.json()["data_count"], 2)

            q = client.post("/api/quality/run", headers=h, params={"dataset_id": ds_id})
            self.assertEqual(q.status_code, 200, q.text)

            model = client.post("/api/models", json={"name": "mock-llm", "api_url": ""}, headers=h)
            self.assertEqual(model.status_code, 200, model.text)
            model_id = model.json()["id"]

            prompt = client.post("/api/prompts", json={
                "name": "qa-prompt",
                "prompt_content": "{{input}}",
            }, headers=h)
            self.assertEqual(prompt.status_code, 200, prompt.text)

            inv = client.post("/api/resources/invoke", json={
                "resource_id": "builtin/exact_match",
                "body": {"prediction": "北京", "reference": "北京"},
            }, headers=h)
            self.assertEqual(inv.status_code, 200, inv.text)
            self.assertEqual(inv.json()["header"]["status"], "ok")

            task = client.post("/api/tasks", json={
                "name": "smoke-task",
                "dataset_id": ds_id,
                "model_id": model_id,
                "prompt_id": prompt.json()["id"],
                "judge_resource_id": "builtin/contains",
            }, headers=h)
            self.assertEqual(task.status_code, 200, task.text)
            task_id = task.json()["id"]
            run = client.post(f"/api/tasks/{task_id}/run", headers=h)
            self.assertEqual(run.status_code, 200, run.text)
            status = ""
            for _ in range(40):
                detail = client.get(f"/api/tasks/{task_id}", headers=h).json()
                status = detail["status"]
                if status in {"success", "failed"}:
                    break
                time.sleep(0.1)
            self.assertEqual(status, "success", detail)
            self.assertGreaterEqual(detail["total"], 2)
            board = client.get("/api/leaderboard", headers=h)
            self.assertEqual(board.status_code, 200)
            stats = client.get("/api/dashboard/stats", headers=h)
            self.assertGreaterEqual(stats.json()["dataset_count"], 1)


if __name__ == "__main__":
    unittest.main()
