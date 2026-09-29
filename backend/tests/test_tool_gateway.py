"""WP02 工具网关 + WP06 MCP/Skill/副作用。"""
from __future__ import annotations

import unittest
import uuid

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.main import app
from app.services.protocol import (
    make_envelope,
    make_response,
    validate_request_envelope,
    request_hash,
)
from app.services.builtin_tools import run_builtin_tool
from app.services.side_effect_policy import SideEffectBlocked, assert_egress_allowed, stub_side_effect_result
from app.services.skill_runtime import run_skill


class ProtocolEnvelopeTest(unittest.TestCase):
    def test_response_body_status_and_trace_continue(self):
        req = make_envelope("platform", "builtin/exact_match", {"action": "execute", "parameters": {"a": 1}}, caller_id="gateway")
        tid = req["trace"]["trace_id"]
        resp = make_response(req, "success", {"score": 1.0, "passed": True}, usage={"total_tokens": 0})
        self.assertEqual(resp["body"]["status"], "success")
        self.assertEqual(resp["body"]["result"]["score"], 1.0)
        self.assertEqual(resp["body"]["metadata"]["usage"]["total_tokens"], 0)
        self.assertEqual(resp["auth"].get("caller_id"), "gateway")
        self.assertEqual(resp["trace"]["trace_id"], tid)
        self.assertNotEqual(resp["trace"]["span_id"], req["trace"]["span_id"])
        self.assertEqual(resp["header"]["status"], "ok")

    def test_empty_caller_rejected(self):
        env = make_envelope("a", "b", {"action": "execute", "parameters": {}}, caller_id="gateway")
        env["auth"] = {}
        errs = validate_request_envelope(env)
        self.assertTrue(any("caller_id" in e for e in errs))

    def test_request_hash_stable(self):
        a = request_hash({"action": "execute", "parameters": {"x": 1}})
        b = request_hash({"parameters": {"x": 1}, "action": "execute"})
        self.assertEqual(a, b)


class ToolGatewayApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(login.status_code, 200, login.text)
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_invoke_standard_envelope(self):
        cid = str(uuid.uuid4())
        inv = self.client.post(
            "/api/resources/invoke",
            json={
                "resource_id": "builtin/exact_match",
                "correlation_id": cid,
                "body": {"prediction": "北京", "reference": "北京"},
                "tenant_id": "forged-should-ignore",
            },
            headers=self.h,
        )
        self.assertEqual(inv.status_code, 200, inv.text)
        data = inv.json()
        self.assertEqual(data["header"]["status"], "ok")
        self.assertEqual(data["body"]["status"], "success")
        self.assertTrue(data["body"]["result"].get("passed"))
        self.assertEqual(data["header"]["correlation_id"], cid)
        self.assertTrue(data["auth"].get("caller_id"))
        self.assertNotEqual(data["header"].get("tenant_id"), "forged-should-ignore")

    def test_idempotent_same_payload(self):
        cid = f"idem-{uuid.uuid4()}"
        payload = {
            "resource_id": "builtin/exact_match",
            "correlation_id": cid,
            "body": {"prediction": "A", "reference": "A"},
        }
        r1 = self.client.post("/api/resources/invoke", json=payload, headers=self.h)
        r2 = self.client.post("/api/resources/invoke", json=payload, headers=self.h)
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertEqual(r1.json()["body"]["result"], r2.json()["body"]["result"])
        self.assertEqual(r1.json()["header"]["correlation_id"], r2.json()["header"]["correlation_id"])

    def test_idempotent_conflict_different_payload(self):
        cid = f"idem-c-{uuid.uuid4()}"
        r1 = self.client.post(
            "/api/resources/invoke",
            json={"resource_id": "builtin/exact_match", "correlation_id": cid, "body": {"prediction": "A", "reference": "A"}},
            headers=self.h,
        )
        self.assertEqual(r1.status_code, 200, r1.text)
        r2 = self.client.post(
            "/api/resources/invoke",
            json={"resource_id": "builtin/exact_match", "correlation_id": cid, "body": {"prediction": "B", "reference": "A"}},
            headers=self.h,
        )
        self.assertEqual(r2.status_code, 409, r2.text)


class SkillRefTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    async def builtin_invoker(step_id: str, resource_id: str, payload: dict) -> dict:
        request = make_envelope(
            "skill-unit",
            resource_id,
            {"action": "execute", "parameters": payload},
            correlation_id=f"unit:{step_id}",
            caller_id="skill_step",
        )
        return make_response(
            request,
            "success",
            run_builtin_tool(resource_id, payload),
        )

    async def test_workflow_input_binding(self):
        mf = {
            "skill": {
                "execution_type": "workflow",
                "chain": [
                    {
                        "step_id": "a",
                        "resource_id": "builtin/exact_match",
                        "input": {
                            "prediction": {"$ref": "$input.prediction"},
                            "reference": {"$ref": "$input.reference"},
                        },
                    }
                ],
            }
        }
        out = await run_skill(
            mf,
            {"prediction": "北京", "reference": "北京"},
            step_invoker=self.builtin_invoker,
        )
        self.assertTrue(out["passed"])
        self.assertEqual(out["steps"][0]["step_id"], "a")

    async def test_forward_ref_rejected(self):
        mf = {
            "skill": {
                "execution_type": "workflow",
                "chain": [
                    {
                        "step_id": "a",
                        "resource_id": "builtin/exact_match",
                        "input": {"prediction": {"$ref": "step_1.output.score"}, "reference": "x"},
                    },
                    {"step_id": "b", "resource_id": "builtin/exact_match", "input": {"prediction": "1", "reference": "1"}},
                ],
            }
        }
        with self.assertRaises(ValueError):
            await run_skill(mf, {}, step_invoker=self.builtin_invoker)

    async def test_non_workflow_rejected(self):
        mf = {"skill": {"execution_type": "code", "chain": [{"$ref": "builtin/exact_match"}]}}
        with self.assertRaises(ValueError):
            await run_skill(
                mf,
                {"prediction": "a", "reference": "a"},
                step_invoker=self.builtin_invoker,
            )


class SideEffectPolicyTest(unittest.TestCase):
    def test_stub_result(self):
        mf = {"side_effects": [{"type": "network", "mock_strategy": "stub"}]}
        with self.assertRaises(SideEffectBlocked) as ctx:
            stub_side_effect_result(mf)
        self.assertEqual(ctx.exception.code, "SIDE_EFFECT_BLOCKED")

    def test_deny(self):
        mf = {"side_effects": [{"type": "fs", "mock_strategy": "deny"}]}
        with self.assertRaises(PermissionError):
            stub_side_effect_result(mf)

    def test_egress_allowlist(self):
        mf = {"interfaces": {"egress_allowlist": ["api.example.com"]}}
        assert_egress_allowed("https://api.example.com/v1", mf)
        with self.assertRaises(PermissionError):
            assert_egress_allowed("https://evil.com/x", mf)


class McpSkillApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_builtin_mcp_initialize(self):
        inv = self.client.post(
            "/api/resources/invoke",
            json={"resource_id": "builtin/mcp_gateway", "body": {"method": "initialize", "id": 1}},
            headers=self.h,
        )
        self.assertEqual(inv.status_code, 200, inv.text)
        data = inv.json()
        self.assertEqual(data["body"]["status"], "success")
        result = data["body"]["result"]
        inner = result.get("result") if isinstance(result.get("result"), dict) else result
        self.assertIn("protocolVersion", inner)

    def test_mcp_probe_local_via_resource(self):
        probe = self.client.post(
            "/api/resources/mcp/probe",
            json={"resource_id": "builtin/mcp_gateway", "method": "tools/list"},
            headers=self.h,
        )
        self.assertEqual(probe.status_code, 200, probe.text)
        body = probe.json()
        self.assertEqual(body.get("mode"), "registered")
        self.assertEqual(body.get("target"), "builtin/mcp_gateway")
        result = body.get("result") or {}
        inner = result.get("result") if isinstance(result.get("result"), dict) else result
        tools = inner.get("tools") or []
        self.assertGreaterEqual(len(tools), 1)

    def test_mcp_probe_source_mutex(self):
        both = self.client.post(
            "/api/resources/mcp/probe",
            json={
                "resource_id": "builtin/mcp_gateway",
                "endpoint": "http://127.0.0.1:9/mcp",
                "method": "initialize",
            },
            headers=self.h,
        )
        self.assertEqual(both.status_code, 400, both.text)
        payload = both.json()
        detail = payload.get("detail") or payload.get("message") or both.text
        self.assertIn("mcp_source_mutex", str(detail))

        empty = self.client.post(
            "/api/resources/mcp/probe",
            json={"method": "initialize"},
            headers=self.h,
        )
        self.assertEqual(empty.status_code, 400, empty.text)

    def test_skill_invoke_still_works(self):
        inv = self.client.post(
            "/api/resources/invoke",
            json={"resource_id": "builtin/skill_dual_judge", "body": {"prediction": "北京", "reference": "北京"}},
            headers=self.h,
        )
        self.assertEqual(inv.status_code, 200, inv.text)
        self.assertTrue(inv.json()["body"]["result"].get("passed"))

    def test_side_effect_stub_via_register(self):
        rid = f"demo/side_effect_tool_{uuid.uuid4().hex[:6]}"
        mf = {
            "spec_version": "0.6.1",
            "resource_id": rid,
            "resource_type": "tool",
            "name": "副作用样例",
            "description": "side effect stub fixture",
            "version": "1.0.0",
            "owner": {"name": "t", "contact": "t", "email": "t@t.com"},
            "capabilities": {
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "call_mode": "sync",
                "idempotent": True,
                "timeout": 10,
            },
            "interfaces": {"endpoint": "https://example.com/x", "method": "POST", "auth_type": "none"},
            "side_effects": [{"type": "network", "mock_strategy": "stub"}],
        }
        reg = self.client.post("/api/resources/register", json={"manifest": mf}, headers=self.h)
        self.assertEqual(reg.status_code, 200, reg.text)
        inv = self.client.post("/api/resources/invoke", json={"resource_id": rid, "body": {}}, headers=self.h)
        self.assertEqual(inv.status_code, 200, inv.text)
        body = inv.json()["body"]
        self.assertEqual(body.get("status"), "error")
        self.assertEqual(body.get("error", {}).get("code"), "SIDE_EFFECT_BLOCKED")
        self.assertFalse((body.get("result") or {}).get("stubbed"))


if __name__ == "__main__":
    unittest.main()
