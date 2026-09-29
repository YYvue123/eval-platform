from __future__ import annotations

from tests import isolated_env  # noqa: F401

import asyncio
import copy
import json
import os
import socket
import sys
import threading
import unittest
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import async_session
from app.main import app
from app.models import BaseResource
from app.services.mcp.errors import McpError
from app.services.mcp.http_transport import HttpTransport, parse_sse
from app.services.mcp.session import McpSession
from app.services.redaction import evidence_digest, redact_secrets
from tests.followup_helpers import (
    create_other_tenant_admin,
    login_admin,
    stats_service,
    tool_manifest,
)


@contextmanager
def sensitive_error_service(payload=None):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            response_payload = payload or {
                "status": "error",
                "message": {
                    "token": "token-response-secret",
                    "nested": {
                        "api_key": "api-key-response-secret",
                        "authorization": "Bearer response-secret",
                    },
                },
            }
            body = json.dumps(response_payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *args):
            return

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/error"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class ResourceCallEvidenceTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        self.admin_h = login_admin(self.client)

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def _set_online(self, rid: str) -> None:
        async def update() -> None:
            async with async_session() as db:
                resource = await db.scalar(
                    select(BaseResource).where(BaseResource.resource_id == rid)
                )
                resource.status = "online"
                await db.commit()

        asyncio.run(update())

    def test_real_http_call_evidence_history_and_tenant_isolation(self):
        rid = f"demo/stats_{uuid.uuid4().hex[:10]}"
        success_cid = f"success-{uuid.uuid4().hex}"
        failed_cid = f"failed-{uuid.uuid4().hex}"
        with stats_service() as base_url:
            registered = self.client.post(
                "/api/resources/register",
                json={"manifest": tool_manifest(rid, f"{base_url}/v1/stats")},
                headers=self.admin_h,
            )
            self.assertEqual(registered.status_code, 200, registered.text)
            self._set_online(rid)

            success = self.client.post(
                "/api/resources/invoke",
                json={
                    "resource_id": rid,
                    "correlation_id": success_cid,
                    "body": {
                        "values": [{"value": 1, "unit": "m"}],
                        "token": "token-plain-value",
                        "nested": {"Authorization": "Bearer plain-secret"},
                    },
                },
                headers=self.admin_h,
            )
            self.assertEqual(success.status_code, 200, success.text)
            self.assertEqual(success.json()["body"]["status"], "success")
            failed = self.client.post(
                "/api/resources/invoke",
                json={
                    "resource_id": rid,
                    "correlation_id": failed_cid,
                    "body": {"values": []},
                },
                headers=self.admin_h,
            )
            self.assertEqual(failed.status_code, 200, failed.text)
            self.assertEqual(failed.json()["body"]["status"], "error")

        history = self.client.get(
            f"/api/resources/calls/{rid}?page=1&page_size=1",
            headers=self.admin_h,
        )
        self.assertEqual(history.status_code, 200, history.text)
        payload = history.json()
        self.assertEqual(payload["total"], 2)
        self.assertEqual(len(payload["items"]), 1)

        full = self.client.get(
            f"/api/resources/calls/{rid}?page=1&page_size=20",
            headers=self.admin_h,
        )
        self.assertEqual(full.status_code, 200, full.text)
        items = full.json()["items"]
        self.assertEqual({item["status"] for item in items}, {"success", "failed"})
        expected_keys = {
            "id",
            "resource_id",
            "status",
            "latency_ms",
            "error_message",
            "correlation_id",
            "parent_correlation_id",
            "tenant_id",
            "user_id",
            "version",
            "trace_id",
            "input_digest",
            "output_digest",
            "input_hash",
            "output_hash",
            "source",
            "created_at",
        }
        self.assertTrue(all(set(item) == expected_keys for item in items))
        for item in items:
            self.assertGreaterEqual(item["latency_ms"], 0)
            self.assertEqual(len(item["input_hash"]), 64)
            self.assertEqual(len(item["output_hash"]), 64)
            self.assertTrue(item["input_digest"])
            self.assertTrue(item["output_digest"])
            self.assertEqual(item["version"], "1.0.0")
            self.assertTrue(item["trace_id"])
            self.assertEqual(item["source"], "gateway")
        serialized = str(items)
        self.assertNotIn("token-plain-value", serialized)
        self.assertNotIn("Bearer plain-secret", serialized)
        failed_item = next(item for item in items if item["status"] == "failed")
        self.assertTrue(failed_item["error_message"])

        only_failed = self.client.get(
            f"/api/resources/calls/{rid}?status=failed",
            headers=self.admin_h,
        )
        self.assertEqual(only_failed.status_code, 200, only_failed.text)
        self.assertEqual(only_failed.json()["total"], 1)
        self.assertEqual(only_failed.json()["items"][0]["correlation_id"], failed_cid)

        other_h = create_other_tenant_admin(self.client)
        hidden = self.client.get(f"/api/resources/calls/{rid}", headers=other_h)
        self.assertEqual(hidden.status_code, 404, hidden.text)

    def test_http_business_error_never_persists_or_returns_secrets(self):
        rid = f"demo/error_{uuid.uuid4().hex[:10]}"
        correlation_id = f"sensitive-{uuid.uuid4().hex}"
        secrets = (
            "token-response-secret",
            "api-key-response-secret",
            "Bearer response-secret",
        )
        with sensitive_error_service() as endpoint:
            registered = self.client.post(
                "/api/resources/register",
                json={"manifest": tool_manifest(rid, endpoint)},
                headers=self.admin_h,
            )
            self.assertEqual(registered.status_code, 200, registered.text)
            self._set_online(rid)
            response = self.client.post(
                "/api/resources/invoke",
                json={
                    "resource_id": rid,
                    "correlation_id": correlation_id,
                    "body": {"values": [{"value": 1, "unit": "m"}]},
                },
                headers=self.admin_h,
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["body"]["status"], "error")
        response_text = response.text
        for secret in secrets:
            self.assertNotIn(secret, response_text)

        async def load_log():
            from app.models import ResourceCallLog

            async with async_session() as db:
                return await db.scalar(
                    select(ResourceCallLog).where(
                        ResourceCallLog.correlation_id == correlation_id
                    )
                )

        log = asyncio.run(load_log())
        self.assertIsNotNone(log)
        persisted = f"{log.error_message}\n{log.output_digest}"
        for secret in secrets:
            self.assertNotIn(secret, persisted)
        self.assertTrue("redacted" in persisted or "HTTP 工具业务失败" in persisted)

        history = self.client.get(
            f"/api/resources/calls/{rid}",
            headers=self.admin_h,
        )
        self.assertEqual(history.status_code, 200, history.text)
        history_text = history.text
        for secret in secrets:
            self.assertNotIn(secret, history_text)
        self.assertIn("redacted", history_text)

    def test_escaped_runtime_error_uses_safe_gateway_fallback(self):
        rid = f"demo/escaped_{uuid.uuid4().hex[:10]}"
        correlation_id = f"escaped-{uuid.uuid4().hex}"
        secret = "escaped-secret"
        payload = {
            "status": "error",
            "message": r'{\"token\":\"escaped-secret\"}',
        }
        with sensitive_error_service(payload) as endpoint:
            registered = self.client.post(
                "/api/resources/register",
                json={"manifest": tool_manifest(rid, endpoint)},
                headers=self.admin_h,
            )
            self.assertEqual(registered.status_code, 200, registered.text)
            self._set_online(rid)
            response = self.client.post(
                "/api/resources/invoke",
                json={
                    "resource_id": rid,
                    "correlation_id": correlation_id,
                    "body": {},
                },
                headers=self.admin_h,
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(secret, response.text)

        async def load_log():
            from app.models import ResourceCallLog

            async with async_session() as db:
                return await db.scalar(
                    select(ResourceCallLog).where(
                        ResourceCallLog.correlation_id == correlation_id
                    )
                )

        log = asyncio.run(load_log())
        self.assertIsNotNone(log)
        self.assertNotIn(secret, log.error_message)
        self.assertNotIn(secret, log.output_digest)
        history = self.client.get(
            f"/api/resources/calls/{rid}",
            headers=self.admin_h,
        )
        self.assertEqual(history.status_code, 200, history.text)
        self.assertNotIn(secret, history.text)

    def test_builtin_history_is_partitioned_by_calling_tenant(self):
        other_h = create_other_tenant_admin(self.client)
        rid = "builtin/exact_match"
        admin_cid = f"admin-{uuid.uuid4().hex}"
        other_cid = f"other-{uuid.uuid4().hex}"
        for headers, correlation in (
            (self.admin_h, admin_cid),
            (other_h, other_cid),
        ):
            response = self.client.post(
                "/api/resources/invoke",
                json={
                    "resource_id": rid,
                    "correlation_id": correlation,
                    "body": {"prediction": "x", "reference": "x"},
                },
                headers=headers,
            )
            self.assertEqual(response.status_code, 200, response.text)

        admin_items = self.client.get(
            f"/api/resources/calls/{rid}?page_size=100",
            headers=self.admin_h,
        ).json()["items"]
        other_items = self.client.get(
            f"/api/resources/calls/{rid}?page_size=100",
            headers=other_h,
        ).json()["items"]
        self.assertIn(admin_cid, {item["correlation_id"] for item in admin_items})
        self.assertNotIn(other_cid, {item["correlation_id"] for item in admin_items})
        self.assertIn(other_cid, {item["correlation_id"] for item in other_items})
        self.assertNotIn(admin_cid, {item["correlation_id"] for item in other_items})
        self.assertEqual(
            {item["tenant_id"] for item in other_items},
            {other_items[0]["tenant_id"]},
        )


class SkillGatewayTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        self.admin_h = login_admin(self.client)

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def _set_online(self, *resource_ids: str) -> None:
        async def update() -> None:
            async with async_session() as db:
                for resource_id in resource_ids:
                    resource = await db.scalar(
                        select(BaseResource).where(
                            BaseResource.resource_id == resource_id
                        )
                    )
                    resource.status = "online"
                await db.commit()

        asyncio.run(update())

    @staticmethod
    def _skill_manifest(rid: str, chain: list[dict]) -> dict:
        return {
            "spec_version": "0.6.1",
            "resource_id": rid,
            "resource_type": "skill",
            "name": "gateway workflow skill",
            "description": "Task 6 gateway workflow fixture",
            "version": "1.0.0",
            "owner": {
                "name": "test",
                "contact": "test",
                "email": "test@example.com",
            },
            "capabilities": {
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "call_mode": "sync",
                "idempotent": True,
                "timeout": 10,
                "side_effects": "none",
            },
            "interfaces": {},
            "skill": {"execution_type": "workflow", "chain": chain},
        }

    def test_real_http_steps_share_parent_trace_and_history(self):
        suffix = uuid.uuid4().hex[:10]
        parse_rid = f"demo/parse_{suffix}"
        stats_rid = f"demo/stats_{suffix}"
        skill_rid = f"demo/skill_{suffix}"
        parent_cid = f"skill-{uuid.uuid4().hex}"
        with stats_service() as base_url:
            for rid, endpoint in (
                (parse_rid, f"{base_url}/v1/parse"),
                (stats_rid, f"{base_url}/v1/stats"),
            ):
                registered = self.client.post(
                    "/api/resources/register",
                    json={"manifest": tool_manifest(rid, endpoint)},
                    headers=self.admin_h,
                )
                self.assertEqual(registered.status_code, 200, registered.text)
            self._set_online(parse_rid, stats_rid)
            manifest = self._skill_manifest(
                skill_rid,
                [
                    {
                        "step_id": "s1",
                        "resource_id": parse_rid,
                        "input": {"text": {"$ref": "$input.text"}},
                    },
                    {
                        "step_id": "s2",
                        "resource_id": stats_rid,
                        "input": {
                            "values": {"$ref": "s1.output.values"},
                            "target_unit": {"$ref": "$input.target_unit"},
                        },
                    },
                ],
            )
            registered = self.client.post(
                "/api/resources/register",
                json={"manifest": manifest},
                headers=self.admin_h,
            )
            self.assertEqual(registered.status_code, 200, registered.text)
            invoked = self.client.post(
                "/api/resources/invoke",
                json={
                    "resource_id": skill_rid,
                    "correlation_id": parent_cid,
                    "body": {
                        "text": "100 cm, 2 m, 500 mm",
                        "target_unit": "m",
                    },
                },
                headers=self.admin_h,
            )

        self.assertEqual(invoked.status_code, 200, invoked.text)
        payload = invoked.json()
        self.assertEqual(payload["body"]["status"], "success")
        result = payload["body"]["result"]
        self.assertEqual(result["result"]["converted"], [1.0, 2.0, 0.5])
        self.assertAlmostEqual(result["result"]["mean"], 3.5 / 3)
        self.assertIsNone(result["score"])
        self.assertIsNone(result["passed"])

        parent_history = self.client.get(
            f"/api/resources/calls/{skill_rid}", headers=self.admin_h
        ).json()["items"][0]
        child_rows = []
        for rid, step_id in ((parse_rid, "s1"), (stats_rid, "s2")):
            history = self.client.get(
                f"/api/resources/calls/{rid}", headers=self.admin_h
            )
            self.assertEqual(history.status_code, 200, history.text)
            row = history.json()["items"][0]
            child_rows.append(row)
            self.assertEqual(row["source"], "skill_step")
            self.assertEqual(row["parent_correlation_id"], parent_cid)
            self.assertEqual(row["trace_id"], parent_history["trace_id"])
            self.assertEqual(row["correlation_id"], f"{parent_cid}:{step_id}")
        self.assertNotEqual(
            child_rows[0]["correlation_id"], child_rows[1]["correlation_id"]
        )

    def test_registration_enforces_acl_and_rejects_nested_skill(self):
        suffix = uuid.uuid4().hex[:10]
        private_tool = f"demo/private_{suffix}"
        with stats_service() as base_url:
            registered = self.client.post(
                "/api/resources/register",
                json={
                    "manifest": tool_manifest(
                        private_tool, f"{base_url}/v1/stats"
                    )
                },
                headers=self.admin_h,
            )
            self.assertEqual(registered.status_code, 200, registered.text)

        other_h = create_other_tenant_admin(self.client)
        hidden = self.client.post(
            "/api/resources/register",
            json={
                "manifest": self._skill_manifest(
                    f"demo/hidden_ref_{suffix}",
                    [{"step_id": "s1", "resource_id": private_tool}],
                )
            },
            headers=other_h,
        )
        self.assertEqual(hidden.status_code, 400, hidden.text)
        self.assertIn("skill.chain[0]", hidden.text)

        inner_rid = f"demo/inner_{suffix}"
        inner = self.client.post(
            "/api/resources/register",
            json={
                "manifest": self._skill_manifest(
                    inner_rid,
                    [
                        {
                            "step_id": "s1",
                            "resource_id": "builtin/exact_match",
                        }
                    ],
                )
            },
            headers=self.admin_h,
        )
        self.assertEqual(inner.status_code, 200, inner.text)
        outer = self.client.post(
            "/api/resources/register",
            json={
                "manifest": self._skill_manifest(
                    f"demo/outer_{suffix}",
                    [{"step_id": "s1", "resource_id": inner_rid}],
                )
            },
            headers=self.admin_h,
        )
        self.assertEqual(outer.status_code, 400, outer.text)
        self.assertIn("Skill 不允许嵌套 Skill", outer.text)

    def test_downstream_failure_is_safe_logged_and_not_idempotent(self):
        suffix = uuid.uuid4().hex[:10]
        stats_rid = f"demo/failing_stats_{suffix}"
        skill_rid = f"demo/failing_skill_{suffix}"
        parent_cid = f"skill-failed-{uuid.uuid4().hex}"
        with stats_service() as base_url:
            registered = self.client.post(
                "/api/resources/register",
                json={
                    "manifest": tool_manifest(
                        stats_rid, f"{base_url}/v1/stats"
                    )
                },
                headers=self.admin_h,
            )
            self.assertEqual(registered.status_code, 200, registered.text)
            self._set_online(stats_rid)
            skill = self.client.post(
                "/api/resources/register",
                json={
                    "manifest": self._skill_manifest(
                        skill_rid,
                        [
                            {
                                "step_id": "stats",
                                "resource_id": stats_rid,
                                "input": {"values": {"$ref": "$input.values"}},
                            }
                        ],
                    )
                },
                headers=self.admin_h,
            )
            self.assertEqual(skill.status_code, 200, skill.text)
            failed = self.client.post(
                "/api/resources/invoke",
                json={
                    "resource_id": skill_rid,
                    "correlation_id": parent_cid,
                    "body": {"values": []},
                },
                headers=self.admin_h,
            )

        self.assertEqual(failed.status_code, 200, failed.text)
        body = failed.json()["body"]
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], "TOOL_EXEC_FAILED")
        self.assertIn("stats", body["error"]["message"])
        history = self.client.get(
            f"/api/resources/calls/{stats_rid}", headers=self.admin_h
        ).json()["items"][0]
        self.assertEqual(history["status"], "failed")
        self.assertEqual(history["source"], "skill_step")
        self.assertNotIn("样本不能为空", failed.text)

        async def parent_idempotency_count() -> int:
            from app.models import IdempotencyRecord

            async with async_session() as db:
                rows = (
                    await db.execute(
                        select(IdempotencyRecord).where(
                            IdempotencyRecord.resource_id == skill_rid,
                            IdempotencyRecord.correlation_id == parent_cid,
                        )
                    )
                ).scalars().all()
                return len(rows)

        self.assertEqual(asyncio.run(parent_idempotency_count()), 0)

    def test_step_http_exception_returns_skill_error_envelope(self):
        suffix = uuid.uuid4().hex[:10]
        tool_rid = f"demo/offline_step_{suffix}"
        skill_rid = f"demo/offline_skill_{suffix}"
        parent_cid = f"skill-offline-{uuid.uuid4().hex}"
        registered = self.client.post(
            "/api/resources/register",
            json={
                "manifest": tool_manifest(
                    tool_rid, "http://127.0.0.1:1/v1/stats"
                )
            },
            headers=self.admin_h,
        )
        self.assertEqual(registered.status_code, 200, registered.text)
        skill = self.client.post(
            "/api/resources/register",
            json={
                "manifest": self._skill_manifest(
                    skill_rid,
                    [
                        {
                            "step_id": "offline_step",
                            "resource_id": tool_rid,
                            "input": {"values": {"$ref": "$input.values"}},
                        }
                    ],
                )
            },
            headers=self.admin_h,
        )
        self.assertEqual(skill.status_code, 200, skill.text)
        offline = self.client.post(
            f"/api/resources/{tool_rid}/offline",
            headers=self.admin_h,
        )
        self.assertEqual(offline.status_code, 200, offline.text)
        failed = self.client.post(
            "/api/resources/invoke",
            json={
                "resource_id": skill_rid,
                "correlation_id": parent_cid,
                "body": {"values": [1]},
            },
            headers=self.admin_h,
        )
        self.assertEqual(failed.status_code, 200, failed.text)
        body = failed.json()["body"]
        self.assertEqual(body["status"], "error")
        self.assertIn("offline_step", body["error"]["message"])

        async def parent_idempotency_count() -> int:
            from app.models import IdempotencyRecord

            async with async_session() as db:
                rows = (
                    await db.execute(
                        select(IdempotencyRecord).where(
                            IdempotencyRecord.resource_id == skill_rid,
                            IdempotencyRecord.correlation_id == parent_cid,
                        )
                    )
                ).scalars().all()
                return len(rows)

        self.assertEqual(asyncio.run(parent_idempotency_count()), 0)

    def test_historical_nested_manifest_is_rejected_at_runtime(self):
        suffix = uuid.uuid4().hex[:10]
        inner_rid = f"demo/history_inner_{suffix}"
        outer_rid = f"demo/history_outer_{suffix}"
        inner = self.client.post(
            "/api/resources/register",
            json={
                "manifest": self._skill_manifest(
                    inner_rid,
                    [
                        {
                            "step_id": "judge",
                            "resource_id": "builtin/exact_match",
                        }
                    ],
                )
            },
            headers=self.admin_h,
        )
        self.assertEqual(inner.status_code, 200, inner.text)
        outer_manifest = self._skill_manifest(
            outer_rid,
            [
                {
                    "step_id": "legacy_nested",
                    "resource_id": "builtin/exact_match",
                }
            ],
        )
        outer = self.client.post(
            "/api/resources/register",
            json={"manifest": outer_manifest},
            headers=self.admin_h,
        )
        self.assertEqual(outer.status_code, 200, outer.text)

        async def inject_historical_manifest() -> None:
            from app.models import ResourceVersion
            from app.utils.jsonutil import dumps

            historical = copy.deepcopy(outer_manifest)
            historical["skill"]["chain"][0]["resource_id"] = inner_rid
            async with async_session() as db:
                resource = await db.scalar(
                    select(BaseResource).where(
                        BaseResource.resource_id == outer_rid
                    )
                )
                version = await db.scalar(
                    select(ResourceVersion).where(
                        ResourceVersion.resource_id == outer_rid,
                        ResourceVersion.version == "1.0.0",
                    )
                )
                resource.manifest_json = dumps(historical)
                version.manifest_json = dumps(historical)
                await db.commit()

        asyncio.run(inject_historical_manifest())
        invoked = self.client.post(
            "/api/resources/invoke",
            json={
                "resource_id": outer_rid,
                "body": {"prediction": "x", "reference": "x"},
            },
            headers=self.admin_h,
        )
        self.assertEqual(invoked.status_code, 200, invoked.text)
        self.assertEqual(invoked.json()["body"]["status"], "error")
        self.assertIn("嵌套", invoked.json()["body"]["error"]["message"])


class RedactionTest(unittest.TestCase):
    def test_escaped_error_text_and_unquoted_boundaries(self):
        from app.services.redaction import redact_error_text

        escaped_token = redact_error_text(r'{\"token\":\"escaped-secret\"}')
        escaped_auth = redact_error_text(
            r'{\"authorization\":\"Bearer escaped-auth\"}'
        )
        prefixed_escaped = redact_error_text(
            r'upstream {\"token\":\"prefixed-secret\"}; retry available'
        )
        semicolon = redact_error_text("token=abc; retry after 30 seconds")
        ampersand = redact_error_text("token=abc&request_id=42")
        self.assertNotIn("escaped-secret", escaped_token)
        self.assertNotIn("Bearer escaped-auth", escaped_auth)
        self.assertNotIn("prefixed-secret", prefixed_escaped)
        self.assertIn("retry available", prefixed_escaped)
        self.assertIn("retry after 30 seconds", semicolon)
        self.assertIn("request_id=42", ampersand)

    def test_error_formatting_redacts_structured_and_stringified_secrets(self):
        from app.services.redaction import safe_error_message, sanitize_error_text

        secrets = ("dict-token", "dict-key", "python-secret", "Bearer text-secret")
        structured = safe_error_message(
            {
                "token": secrets[0],
                "nested": {"api_key": secrets[1]},
            }
        )
        stringified = sanitize_error_text(
            "{'password': 'python-secret', "
            "'authorization': 'Bearer text-secret'}"
        )
        combined = structured + stringified
        for secret in secrets:
            self.assertNotIn(secret, combined)
        self.assertIn("redacted", structured)
        self.assertIn("redacted", stringified)

    def test_recursive_redaction_preserves_reference_without_mutation(self):
        original = {
            "token": "secret-token",
            "nested": [
                {"Authorization": "Bearer secret"},
                {"credential": "secret-credential"},
                {"credential_ref": "STATS_API_TOKEN"},
            ],
        }
        before = copy.deepcopy(original)
        redacted = redact_secrets(original)
        marker = {"configured": True, "redacted": True}
        self.assertEqual(original, before)
        self.assertEqual(redacted["token"], marker)
        self.assertEqual(redacted["nested"][0]["Authorization"], marker)
        self.assertEqual(redacted["nested"][1]["credential"], marker)
        self.assertEqual(redacted["nested"][2]["credential_ref"], "STATS_API_TOKEN")

    def test_hash_uses_complete_json_before_digest_truncation(self):
        common = "x" * 4100
        left_digest, left_hash = evidence_digest({"value": common + "a"})
        right_digest, right_hash = evidence_digest({"value": common + "b"})
        self.assertEqual(left_digest, right_digest)
        self.assertEqual(len(left_digest), 4000)
        self.assertNotEqual(left_hash, right_hash)


class ParseSseTest(unittest.TestCase):
    def test_parse_sse_joins_data_and_captures_id(self):
        events = parse_sse(
            [
                "id: 7",
                "event: message",
                "data: {\"ok\":true}",
                "",
                "data: leftover-without-blank",
            ]
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["id"], "7")
        self.assertEqual(events[0]["event"], "message")
        self.assertEqual(events[0]["data"], '{"ok":true}')

    def test_ingest_event_requires_request_id_match(self):
        transport = HttpTransport("http://127.0.0.1:9/mcp", timeout=1, channel="plain")
        note = {
            "event": "message",
            "id": "n1",
            "data": json.dumps({"jsonrpc": "2.0", "method": "notifications/foo"}),
        }
        try:
            self.assertIsNone(transport._ingest_event(note, None))
            self.assertEqual(transport.notifications[-1]["method"], "notifications/foo")
            matched = {
                "event": "message",
                "id": "r1",
                "data": json.dumps({"jsonrpc": "2.0", "id": 3, "result": {"ok": True}}),
            }
            payload = transport._ingest_event(matched, 3)
            self.assertEqual(payload["result"]["ok"], True)
            self.assertIsNone(transport._ingest_event(matched, 4))
        finally:
            asyncio.run(transport.close())


class McpHttpTransportTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = stats_service()
        self.base_url = self.server.__enter__()

    async def asyncTearDown(self):
        self.server.__exit__(None, None, None)

    async def test_initialize_notification_and_paginated_catalog(self):
        session = McpSession(HttpTransport(f"{self.base_url}/mcp", timeout=5))
        info = await session.open()
        tools = await session.list_tools()
        self.assertEqual(info["protocolVersion"], "2024-11-05")
        self.assertEqual(
            [x["name"] for x in tools],
            ["parse_measurements", "compute_stats"],
        )
        self.assertTrue(session.session_id_present)
        await session.close()

    async def test_json_and_sse_tool_call(self):
        session = McpSession(HttpTransport(f"{self.base_url}/mcp", timeout=5))
        await session.open()
        result = await session.call_tool(
            "parse_measurements",
            {"text": "1 m, 20 cm", "_meta": {"stream": True}},
        )
        self.assertEqual(len(result["structuredContent"]), 2)
        await session.close()

    async def test_tool_is_error_has_stable_code(self):
        session = McpSession(HttpTransport(f"{self.base_url}/mcp", timeout=5))
        await session.open()
        with self.assertRaises(McpError) as ctx:
            await session.call_tool("compute_stats", {"values": []})
        self.assertEqual(ctx.exception.code, "MCP_TOOL_ERROR")
        await session.close()

    async def test_list_changed_notification_marks_catalog(self):
        session = McpSession(HttpTransport(f"{self.base_url}/mcp", timeout=5))
        await session.open()
        await session.call_tool(
            "parse_measurements",
            {"text": "1 m", "_meta": {"announce_list_changed": True}},
        )
        self.assertTrue(session.catalog_changed)
        await session.close()

    async def test_interrupted_stream_resumes_with_last_event_id(self):
        session = McpSession(HttpTransport(f"{self.base_url}/mcp", timeout=5))
        await session.open()
        result = await session.call_tool(
            "parse_measurements",
            {"text": "2 kg", "_meta": {"stream": True, "drop_before_response": True}},
        )
        self.assertEqual(result["structuredContent"][0]["unit"], "kg")
        self.assertTrue(session.transport.last_event_id)
        await session.close()


class HttpTransportResumeTest(unittest.IsolatedAsyncioTestCase):
    async def test_send_does_not_resume_with_prior_stream_event_id(self):
        gets: list[str | None] = []
        posts = {"n": 0}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                posts["n"] += 1
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Mcp-Session-Id", "s1")
                self.end_headers()
                if posts["n"] == 1:
                    payload = json.dumps(
                        {"jsonrpc": "2.0", "id": body.get("id"), "result": {"ok": True}}
                    )
                    self.wfile.write(f"id: evt-prior\ndata: {payload}\n\n".encode())

            def do_GET(self):
                gets.append(self.headers.get("Last-Event-ID"))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()

            def do_DELETE(self):
                self.send_response(204)
                self.end_headers()

            def log_message(self, _format, *args):
                return

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        transport = HttpTransport(
            f"http://127.0.0.1:{port}/mcp", timeout=5, channel="plain"
        )
        try:
            first = await transport.send(
                {"jsonrpc": "2.0", "id": 1, "method": "ping"}
            )
            self.assertEqual(first["result"]["ok"], True)
            self.assertEqual(transport.last_event_id, "evt-prior")
            with self.assertRaises(McpError) as ctx:
                await transport.send({"jsonrpc": "2.0", "id": 2, "method": "ping"})
            self.assertEqual(ctx.exception.code, "MCP_TRANSPORT_ERROR")
            self.assertEqual(gets, [])
        finally:
            await transport.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


class McpStdioTransportTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls._old_policy = asyncio.get_event_loop_policy()
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    @classmethod
    def tearDownClass(cls):
        asyncio.set_event_loop_policy(cls._old_policy)

    def setUp(self):
        command = [
            str(Path(sys.executable).resolve()),
            "-m", "tools.stats_service.stdio_server",
        ]
        self.old = os.environ.get("MCP_STDIO_ALLOWLIST")
        os.environ["MCP_STDIO_ALLOWLIST"] = json.dumps({"stats-local": command})
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        self.admin_h = login_admin(self.client)

    def tearDown(self):
        self._cm.__exit__(None, None, None)
        if self.old is None:
            os.environ.pop("MCP_STDIO_ALLOWLIST", None)
        else:
            os.environ["MCP_STDIO_ALLOWLIST"] = self.old

    async def test_allowed_alias_runs_full_lifecycle(self):
        from app.services.mcp.stdio_transport import StdioTransport

        session = McpSession(StdioTransport("stats-local", timeout=5))
        try:
            await session.open()
            tools = await session.list_tools()
            result = await session.call_tool(
                "parse_measurements", {"text": "100 cm"}
            )
            self.assertEqual(len(tools), 2)
            self.assertEqual(result["structuredContent"][0]["unit"], "cm")
        finally:
            await session.close()

    async def test_unknown_alias_is_rejected(self):
        from app.services.mcp.stdio_transport import StdioTransport

        with self.assertRaises(McpError) as ctx:
            StdioTransport("powershell -Command whoami")
        self.assertEqual(ctx.exception.code, "MCP_STDIO_NOT_ALLOWED")

    def test_stdio_aliases_api(self):
        aliases = self.client.get("/api/resources/mcp/stdio-aliases", headers=self.admin_h)
        self.assertEqual(aliases.status_code, 200, aliases.text)
        self.assertEqual(aliases.json()["items"], ["stats-local"])

    def test_stdio_manifest_rejects_command(self):
        rid = f"demo/mcpstdio_{uuid.uuid4().hex[:8]}"
        mf = tool_manifest(rid, "https://example.com/unused")
        mf["resource_type"] = "mcp"
        mf["name"] = "stdio mcp"
        mf["interfaces"] = {
            "transport": "stdio",
            "command_alias": "stats-local",
            "command": ["whoami"],
            "args": ["-Command"],
        }
        rejected = self.client.post(
            "/api/resources/register", json={"manifest": mf}, headers=self.admin_h
        )
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertIn("command_alias", rejected.text)


class McpRunnerApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._old_policy = asyncio.get_event_loop_policy()
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    @classmethod
    def tearDownClass(cls):
        asyncio.set_event_loop_policy(cls._old_policy)

    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        self.headers = login_admin(self.client)
        command = [
            str(Path(sys.executable).resolve()),
            "-m", "tools.stats_service.stdio_server",
        ]
        self.old_allowlist = os.environ.get("MCP_STDIO_ALLOWLIST")
        os.environ["MCP_STDIO_ALLOWLIST"] = json.dumps({"stats-local": command})

    def tearDown(self):
        if self.old_allowlist is None:
            os.environ.pop("MCP_STDIO_ALLOWLIST", None)
        else:
            os.environ["MCP_STDIO_ALLOWLIST"] = self.old_allowlist
        self._cm.__exit__(None, None, None)

    def register_mcp(self, rid, interfaces):
        manifest = tool_manifest(rid, "https://unused")
        manifest.update({
            "resource_type": "mcp",
            "interfaces": interfaces,
        })
        response = self.client.post(
            "/api/resources/register",
            json={"manifest": manifest},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)

    def probe(self, rid, method, params=None):
        return self.client.post(
            "/api/resources/mcp/probe",
            json={
                "resource_id": rid,
                "method": method,
                "params": params or {},
            },
            headers=self.headers,
        )

    def test_registered_http_mcp_full_flow_and_probe_log(self):
        rid = f"demo/mcp_http_{uuid.uuid4().hex[:8]}"
        with stats_service() as base_url:
            self.register_mcp(rid, {
                "transport": "streamable_http",
                "endpoint": f"{base_url}/mcp",
                "method": "POST",
            })
            initialized = self.probe(rid, "initialize")
            listed = self.probe(rid, "tools/list")
            called = self.probe(rid, "tools/call", {
                "name": "parse_measurements",
                "arguments": {"text": "1 m, 20 cm"},
            })
        self.assertTrue(initialized.json()["ok"])
        self.assertEqual(
            initialized.json()["session"]["protocol_version"],
            "2024-11-05",
        )
        self.assertTrue(initialized.json()["session"]["session_id_present"])
        self.assertEqual(len(listed.json()["result"]["tools"]), 2)
        self.assertTrue(called.json()["ok"])
        history = self.client.get(
            f"/api/resources/calls/{rid}",
            headers=self.headers,
        ).json()
        self.assertGreaterEqual(history["total"], 3)
        self.assertTrue(all(x["source"] == "mcp_probe" for x in history["items"]))

    def test_registered_stdio_mcp_full_flow(self):
        rid = f"demo/mcp_stdio_{uuid.uuid4().hex[:8]}"
        self.register_mcp(rid, {
            "transport": "stdio",
            "command_alias": "stats-local",
        })
        listed = self.probe(rid, "tools/list")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertTrue(listed.json()["ok"])
        self.assertEqual(len(listed.json()["result"]["tools"]), 2)

    def test_tool_is_error_is_not_green(self):
        rid = f"demo/mcp_error_{uuid.uuid4().hex[:8]}"
        with stats_service() as base_url:
            self.register_mcp(rid, {
                "transport": "streamable_http",
                "endpoint": f"{base_url}/mcp",
                "method": "POST",
            })
            response = self.probe(rid, "tools/call", {
                "name": "compute_stats",
                "arguments": {"values": []},
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(response.json()["error"]["code"], "MCP_TOOL_ERROR")
        history = self.client.get(
            f"/api/resources/calls/{rid}",
            headers=self.headers,
        ).json()
        self.assertEqual(history["items"][0]["status"], "failed")

    def test_catalog_change_event_marks_detail_stale(self):
        rid = f"demo/mcp_stale_{uuid.uuid4().hex[:8]}"
        with stats_service() as base_url:
            self.register_mcp(rid, {
                "transport": "streamable_http",
                "endpoint": f"{base_url}/mcp",
                "method": "POST",
            })
            listed = self.probe(rid, "tools/list")
            self.assertTrue(listed.json()["ok"])
            changed = self.probe(rid, "tools/call", {
                "name": "parse_measurements",
                "arguments": {
                    "text": "1 m",
                    "_meta": {"announce_list_changed": True},
                },
            })
            self.assertTrue(changed.json()["ok"])
        detail = self.client.get(
            f"/api/resources/{rid}",
            headers=self.headers,
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertTrue(detail.json()["mcp_catalog"]["stale"])
