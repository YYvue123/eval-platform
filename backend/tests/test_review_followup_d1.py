"""复审 R02/R03/R04/R08/R10/R12：可信执行与权限。"""
from __future__ import annotations

import hashlib
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.main import app
from app.services.http_adapter import invoke_http_tool
from app.services.side_effect_policy import has_side_effects


def _manifest(rid: str, **extra) -> dict:
    mf = {
        "spec_version": "0.6.1",
        "resource_id": rid,
        "resource_type": "tool",
        "name": "review tool",
        "description": "review fixture",
        "version": "1.0.0",
        "owner": {"name": "t", "contact": "t", "email": "t@t.com"},
        "capabilities": {
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "call_mode": "sync",
            "idempotent": True,
            "timeout": 10,
            "side_effects": "none",
        },
        "interfaces": {"endpoint": "https://example.com/x", "method": "POST", "auth_type": "none"},
    }
    mf.update(extra)
    return mf


class SideEffectTypeTest(unittest.TestCase):
    def test_capabilities_none_string_is_not_effect(self):
        self.assertFalse(has_side_effects({"capabilities": {"side_effects": "none"}}))

    def test_capabilities_empty_list_and_bool_false(self):
        self.assertFalse(has_side_effects({"capabilities": {"side_effects": []}}))
        self.assertFalse(has_side_effects({"capabilities": {"side_effects": False}}))
        self.assertFalse(has_side_effects({"capabilities": {"side_effects": ""}}))

    def test_list_and_nonempty_string_are_effects(self):
        self.assertTrue(has_side_effects({"capabilities": {"side_effects": ["network"]}}))
        self.assertTrue(has_side_effects({"side_effects": "network"}))
        self.assertTrue(has_side_effects({"capabilities": {"side_effects": True}}))


class SideEffectInvokeTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_stub_strategy_is_not_success(self):
        rid = f"demo/side_{uuid.uuid4().hex[:8]}"
        mf = _manifest(rid, side_effects=[{"type": "network", "mock_strategy": "stub"}])
        reg = self.client.post("/api/resources/register", json={"manifest": mf}, headers=self.h)
        self.assertEqual(reg.status_code, 200, reg.text)
        self.assertNotEqual(reg.json().get("health_status"), "online")
        inv = self.client.post("/api/resources/invoke", json={"resource_id": rid, "body": {}}, headers=self.h)
        self.assertEqual(inv.status_code, 200, inv.text)
        body = inv.json()["body"]
        self.assertNotEqual(body.get("status"), "success")
        result = body.get("result") or {}
        self.assertFalse(result.get("stubbed"))
        self.assertIn(body.get("error", {}).get("code"), {"SIDE_EFFECT_BLOCKED", "SIDE_EFFECT_DENIED"})


class ResourceAclTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.admin_h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_other_tenant_cannot_read_or_invoke(self):
        import asyncio
        from sqlalchemy import select
        from app.database import async_session
        from app.models import Role, Tenant, TenantMembership, User
        from app.utils.auth import get_password_hash

        rid = f"demo/priv_{uuid.uuid4().hex[:8]}"
        reg = self.client.post(
            "/api/resources/register",
            json={"manifest": _manifest(rid)},
            headers=self.admin_h,
        )
        self.assertEqual(reg.status_code, 200, reg.text)
        from app.models import BaseResource

        async def _force_online():
            async with async_session() as db:
                row = await db.scalar(select(BaseResource).where(BaseResource.resource_id == rid))
                row.status = "online"
                await db.commit()

        asyncio.run(_force_online())

        async def _user_b():
            async with async_session() as db:
                t = Tenant(code=f"tb-{uuid.uuid4().hex[:6]}", name="B", status="active")
                db.add(t)
                await db.flush()
                role = await db.scalar(select(Role).where(Role.code == "admin"))
                uname = f"admb-{uuid.uuid4().hex[:6]}"
                u = User(
                    username=uname,
                    password_hash=get_password_hash("Test1234!"),
                    role="admin",
                    role_id=role.id if role else None,
                    tenant_id=t.id,
                    status="active",
                )
                db.add(u)
                await db.flush()
                db.add(TenantMembership(tenant_id=t.id, user_id=u.id))
                await db.commit()
                return uname

        uname = asyncio.run(_user_b())
        login = self.client.post("/api/auth/login", json={"username": uname, "password": "Test1234!"})
        self.assertEqual(login.status_code, 200, login.text)
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}

        detail = self.client.get(f"/api/resources/{rid}", headers=h)
        self.assertEqual(detail.status_code, 404, detail.text)
        inv = self.client.post("/api/resources/invoke", json={"resource_id": rid, "body": {}}, headers=h)
        self.assertEqual(inv.status_code, 404, inv.text)
        matched = self.client.post("/api/resources/match", json={"name": rid}, headers=h)
        self.assertEqual(matched.status_code, 200, matched.text)
        self.assertFalse(any(x["resource_id"] == rid for x in matched.json()["items"]))
        reg_items = self.client.get("/api/resources/registry", headers=h).json()["items"]
        self.assertFalse(any(x["resource_id"] == rid for x in reg_items))
        probe = self.client.post("/api/resources/mcp/probe", json={"resource_id": rid}, headers=h)
        self.assertEqual(probe.status_code, 404, probe.text)
        health = self.client.post(f"/api/resources/{rid}/health", headers=h)
        self.assertEqual(health.status_code, 404, health.text)
        hb = self.client.post(f"/api/resources/{rid}/heartbeat", headers=h)
        self.assertEqual(hb.status_code, 404, hb.text)
        own = self.client.get(f"/api/resources/{rid}", headers=self.admin_h)
        self.assertEqual(own.status_code, 200, own.text)
        off = self.client.post(f"/api/resources/{rid}/offline", headers=h)
        self.assertEqual(off.status_code, 404, off.text)
        events = self.client.get("/api/resources/events", headers=h)
        self.assertEqual(events.status_code, 200, events.text)
        self.assertFalse(any(e.get("resource_id") == rid for e in events.json()))


class VersionFreezeTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_same_version_different_manifest_rejected(self):
        rid = f"demo/ver_{uuid.uuid4().hex[:8]}"
        first = _manifest(rid)
        reg = self.client.post("/api/resources/register", json={"manifest": first}, headers=self.h)
        self.assertEqual(reg.status_code, 200, reg.text)
        changed = _manifest(rid)
        changed["interfaces"] = {"endpoint": "https://other.example/y", "method": "POST", "auth_type": "none"}
        again = self.client.post("/api/resources/register", json={"manifest": changed}, headers=self.h)
        self.assertEqual(again.status_code, 409, again.text)


class HttpSuccessContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_http_200_business_error_is_not_success(self):
        envelope = {"header": {}, "trace": {}, "body": {}}
        manifest = {"interfaces": {"endpoint": "https://api.example.com/tool", "method": "POST"}, "capabilities": {"timeout": 5}}
        fake = {"body": {"status": "error", "result": {"ok": True}, "error": {"message": "biz"}}}
        with patch("app.services.http_adapter.httpx.AsyncClient") as client_cls:
            inst = client_cls.return_value.__aenter__.return_value
            resp = AsyncMock()
            resp.status_code = 200
            resp.raise_for_status = lambda: None
            resp.json = lambda: fake
            resp.headers = {}
            inst.request = AsyncMock(return_value=resp)
            with self.assertRaises(RuntimeError):
                await invoke_http_tool(manifest, envelope)

    async def test_missing_status_is_not_success(self):
        envelope = {"header": {}, "trace": {}, "body": {}}
        manifest = {"interfaces": {"endpoint": "https://api.example.com/tool"}, "capabilities": {"timeout": 5}}
        fake = {"body": {"result": {"ok": True}}}
        with patch("app.services.http_adapter.httpx.AsyncClient") as client_cls:
            inst = client_cls.return_value.__aenter__.return_value
            resp = AsyncMock()
            resp.status_code = 200
            resp.raise_for_status = lambda: None
            resp.json = lambda: fake
            resp.headers = {}
            inst.request = AsyncMock(return_value=resp)
            with self.assertRaises(RuntimeError):
                await invoke_http_tool(manifest, envelope)


class DrillEvidenceTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        me = self.client.get("/api/users/me", headers=self.h)
        self.username = me.json().get("username") or "admin"

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_nonempty_strings_do_not_pass(self):
        bad = self.client.post(
            "/api/ops/drills",
            headers=self.h,
            json={
                "drill_type": "restore",
                "result": "pass",
                "evidence": {"sha256": "abc", "rpo_seconds": 0, "signed_by": "someone-else", "evidence_uri": "/tmp/x"},
            },
        )
        self.assertEqual(bad.status_code, 400, bad.text)

    def test_real_artifact_and_self_signer_can_pass(self):
        root = Path(os.environ["BACKUP_DIR"])
        root.mkdir(parents=True, exist_ok=True)
        rel = f"drill-{uuid.uuid4().hex[:8]}.txt"
        path = root / rel
        payload = b"restore-ok"
        path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        ok = self.client.post(
            "/api/ops/drills",
            headers=self.h,
            json={
                "drill_type": "restore",
                "result": "pass",
                "evidence": {
                    "artifact_path": rel,
                    "sha256": digest,
                    "signed_by": self.username,
                    "signed_at": "2026-09-29T00:00:00Z",
                },
            },
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["result"], "pass")


class ShadowNoFakeScoreTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_shadow_does_not_invent_scores(self):
        listed = self.client.get("/api/services/workspaces", headers=self.h)
        self.assertEqual(listed.status_code, 200, listed.text)
        items = listed.json()["items"]
        self.assertTrue(items)
        created = self.client.post(
            "/api/services",
            json={"title": f"sh-{uuid.uuid4().hex[:6]}", "industry": "finance", "requirement": "x", "workspace_id": items[0]["id"]},
            headers=self.h,
        )
        self.assertEqual(created.status_code, 200, created.text)
        sid = created.json()["id"]
        sh = self.client.post(f"/api/services/{sid}/shadow", json={"gray_version": "v-next", "traffic_pct": 0.05}, headers=self.h)
        self.assertEqual(sh.status_code, 200, sh.text)
        shadow = sh.json()["shadow"]
        self.assertEqual(shadow.get("status"), "blocked")
        self.assertEqual(shadow.get("scoring"), "not_run")
        self.assertFalse(shadow.get("promotable"))
        self.assertEqual(int(shadow.get("evidence_pair_count") or 0), 0)
