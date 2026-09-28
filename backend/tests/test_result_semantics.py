"""WP00 结果语义与回归断言（隔离路径见 isolated_env）。"""
from __future__ import annotations

import ast
import importlib
import unittest
from pathlib import Path

# 必须在导入 app 之前设置隔离环境（本模块纯函数测试可不依赖 app.main）
from tests import isolated_env  # noqa: F401

from app.services.builtin_tools import run_builtin_tool


class DependencyRegressionTest(unittest.TestCase):
    def test_sqlalchemy_asyncio_and_greenlet_importable(self):
        importlib.import_module("greenlet")
        importlib.import_module("sqlalchemy.ext.asyncio")
        from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401


class ResultSemanticsTest(unittest.TestCase):
    def test_exact_match_correct_and_wrong(self):
        ok = run_builtin_tool("builtin/exact_match", {"prediction": "北京", "reference": "北京"})
        bad = run_builtin_tool("builtin/exact_match", {"prediction": "上海", "reference": "北京"})
        self.assertEqual(ok["score"], 1.0)
        self.assertTrue(ok["passed"])
        self.assertEqual(bad["score"], 0.0)
        self.assertFalse(bad["passed"])

    def test_hallucination_empty_prediction_not_full_score(self):
        r = run_builtin_tool(
            "builtin/safety_hallucination",
            {"prediction": "", "reference": "北京"},
        )
        self.assertFalse(r["passed"])
        self.assertEqual(r["score"], 0.0)
        self.assertFalse(r.get("demo_only"))

    def test_watermark_empty_prediction_ignores_reference_marks(self):
        r = run_builtin_tool(
            "builtin/safety_watermark",
            {"prediction": "", "reference": "AIGC"},
        )
        self.assertFalse(r["passed"])
        self.assertEqual(r["score"], 0.0)
        self.assertFalse(r.get("demo_only"))

    def test_watermark_requires_mark_in_prediction(self):
        r = run_builtin_tool(
            "builtin/safety_watermark",
            {"prediction": "含 AIGC 标识", "reference": "任意"},
        )
        self.assertTrue(r["passed"])
        self.assertEqual(r["score"], 1.0)


class RunnerSemanticsRegressionTest(unittest.TestCase):
    def test_task_runner_imports_run_builtin_tool(self):
        src = Path(__file__).resolve().parents[1] / "app" / "services" / "task_runner.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        imported = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "builtin_tools" in node.module:
                if any(a.name == "run_builtin_tool" for a in node.names):
                    imported = True
        self.assertTrue(imported)

    def test_eval_result_status_columns_exist(self):
        from app.models.eval_task import EvalResult, EvalTask

        self.assertTrue(hasattr(EvalResult, "execution_status"))
        self.assertTrue(hasattr(EvalResult, "score_status"))
        self.assertTrue(hasattr(EvalResult, "simulation"))
        self.assertTrue(hasattr(EvalTask, "simulation"))


class OpsAcceptanceRegressionTest(unittest.TestCase):
    def test_acceptance_items_are_measured_or_unknown(self):
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            self.assertEqual(login.status_code, 200)
            h = {"Authorization": f"Bearer {login.json()['access_token']}"}
            acc = client.get("/api/ops/acceptance", headers=h)
            self.assertEqual(acc.status_code, 200, acc.text)
            body = acc.json()
            self.assertIn(body.get("ok"), (True, False, None))
            self.assertTrue(body.get("items"))
            for item in body["items"]:
                self.assertIn(item.get("status"), ("measured", "unknown"))
                if item["status"] == "unknown":
                    self.assertIsNone(item.get("ok"))
                # 禁止无证据写死恒 True 冒充通过
                if item["code"] in {"manifest", "errors"}:
                    self.assertEqual(item["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
