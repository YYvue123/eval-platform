"""工具底座 Skill 的健康检查按执行方式区分，不把进程内 Skill 当成 HTTP 服务。"""
from __future__ import annotations

import unittest
import uuid

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.main import app


def _base(rid: str, resource_type: str) -> dict:
    return {
        "spec_version": "0.6.1",
        "resource_id": rid,
        "resource_type": resource_type,
        "name": rid,
        "description": "health fixture",
        "version": "1.0.0",
        "owner": {"name": "test", "contact": "test", "email": "test@example.com"},
        "capabilities": {
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "call_mode": "sync",
            "idempotent": True,
            "timeout": 10,
            "side_effects": "none",
        },
        "interfaces": {"endpoint": "http://127.0.0.1:9/health", "method": "GET", "auth_type": "none"},
    }


class SkillHealthTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(login.status_code, 200, login.text)
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_prompt_skill_is_healthy_without_network(self):
        rid = f"demo/prompt_{uuid.uuid4().hex[:8]}"
        manifest = _base(rid, "skill")
        manifest["interfaces"] = {"method": "prompt_template", "auth_type": "none"}
        manifest["skill"] = {"execution_type": "prompt_template", "entry_point": "只列出缺口。", "trigger": {"type": "context", "value": ""}}
        reg = self.client.post("/api/resources/register", json={"manifest": manifest}, headers=self.h)
        self.assertEqual(reg.status_code, 200, reg.text)
        health = self.client.post(f"/api/resources/{rid}/health", headers=self.h)
        self.assertEqual(health.status_code, 200, health.text)
        body = health.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["status"], "online")

    def test_workflow_skill_checks_referenced_tools(self):
        suffix = uuid.uuid4().hex[:8]
        tool_rid = f"demo/tool_{suffix}"
        skill_rid = f"demo/flow_{suffix}"
        tool = _base(tool_rid, "tool")
        registered = self.client.post("/api/resources/register", json={"manifest": tool}, headers=self.h)
        self.assertEqual(registered.status_code, 200, registered.text)
        skill = _base(skill_rid, "skill")
        skill["interfaces"] = {"method": "workflow", "auth_type": "none"}
        skill["skill"] = {
            "execution_type": "workflow",
            "trigger": {"type": "context", "value": ""},
            "chain": [{"step_id": "s1", "resource_id": tool_rid, "input": {}}],
        }
        reg = self.client.post("/api/resources/register", json={"manifest": skill}, headers=self.h)
        self.assertEqual(reg.status_code, 200, reg.text)
        health = self.client.post(f"/api/resources/{skill_rid}/health", headers=self.h)
        self.assertEqual(health.status_code, 200, health.text)
        self.assertTrue(health.json()["ok"])
        off = self.client.post(f"/api/resources/{tool_rid}/offline", headers=self.h)
        self.assertEqual(off.status_code, 200, off.text)
        again = self.client.post(f"/api/resources/{skill_rid}/health", headers=self.h)
        self.assertFalse(again.json()["ok"])
        self.assertIn(tool_rid, again.json()["detail"])
