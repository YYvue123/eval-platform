"""WP03：数据集修订不可变、模型配置冻结、正式任务门禁。"""
from __future__ import annotations

import json
import time
import unittest
import uuid

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.model_access import assert_channel_allowed
from app.services.prompt_render import MissingRequiredVariable, render_prompt


class DatasetRevisionFreezeTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(login.status_code, 200, login.text)
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_patch_creates_new_version_old_items_unchanged(self):
        ds = self.client.post("/api/datasets", json={"name": f"rev-{int(time.time())}"}, headers=self.h)
        self.assertEqual(ds.status_code, 200, ds.text)
        ds_id = ds.json()["id"]
        payload = json.dumps([{"input": "A", "reference": "1"}, {"input": "B", "reference": "2"}]).encode()
        imp = self.client.post(
            f"/api/datasets/{ds_id}/import",
            headers=self.h,
            files={"file": ("qa.json", payload, "application/json")},
        )
        self.assertEqual(imp.status_code, 200, imp.text)
        detail = self.client.get(f"/api/datasets/{ds_id}", headers=self.h).json()
        old_vid = detail["current_version_id"]
        items = self.client.get(f"/api/datasets/{ds_id}/items", headers=self.h, params={"version_id": old_vid}).json()
        item0 = items["items"][0]
        old_text = item0["input_content"]
        patched = self.client.patch(
            f"/api/datasets/{ds_id}/items/{item0['id']}",
            json={"input_content": "A-patched"},
            headers=self.h,
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        after = self.client.get(f"/api/datasets/{ds_id}", headers=self.h).json()
        self.assertNotEqual(after["current_version_id"], old_vid)
        old_items = self.client.get(f"/api/datasets/{ds_id}/items", headers=self.h, params={"version_id": old_vid}).json()
        self.assertEqual(old_items["items"][0]["input_content"], old_text)
        new_items = self.client.get(
            f"/api/datasets/{ds_id}/items", headers=self.h, params={"version_id": after["current_version_id"]}
        ).json()
        self.assertEqual(new_items["items"][0]["input_content"], "A-patched")


class ModelAccessFreezeTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_update_api_url_keeps_old_access_config(self):
        name = f"m-freeze-{uuid.uuid4().hex[:8]}"
        m = self.client.post(
            "/api/models",
            json={"name": name, "api_url": "https://old.example/v1", "api_key": "k1"},
            headers=self.h,
        )
        self.assertEqual(m.status_code, 200, m.text)
        mid = m.json()["id"]
        old_vid = m.json()["current_version_id"]
        self.assertTrue(old_vid)
        upd = self.client.put(
            f"/api/models/{mid}",
            json={"api_url": "https://new.example/v1"},
            headers=self.h,
        )
        self.assertEqual(upd.status_code, 200, upd.text)
        self.assertNotEqual(upd.json()["current_version_id"], old_vid)
        detail = self.client.get(f"/api/models/{mid}", headers=self.h).json()
        versions = {v["id"]: v for v in detail["versions"]}
        self.assertIn(old_vid, versions)
        # 激活旧版本后 live api_url 应回到旧值
        act = self.client.post(f"/api/models/{mid}/versions/{old_vid}/activate", headers=self.h)
        self.assertEqual(act.status_code, 200, act.text)
        self.assertEqual(act.json()["api_url"], "https://old.example/v1")


class FormalGateAndPromptTest(unittest.TestCase):
    def test_required_variable_strict(self):
        with self.assertRaises(MissingRequiredVariable):
            render_prompt(
                "Q: {{input}}",
                {},
                variable_config=[{"key": "input", "required": True}],
                strict=True,
            )
        out = render_prompt("Q: {{input}}", {"input": "hi"}, variable_config=[{"key": "input", "required": True}])
        self.assertIn("hi", out)

    def test_production_plain_rejected(self):
        old = settings.APP_ENV
        try:
            settings.APP_ENV = "production"
            with self.assertRaises(ValueError):
                assert_channel_allowed("plain")
        finally:
            settings.APP_ENV = old

    def test_publish_requires_quality(self):
        with TestClient(app) as client:
            token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
            h = {"Authorization": f"Bearer {token}"}
            ds = client.post("/api/datasets", json={"name": f"pub-{int(time.time())}"}, headers=h).json()
            payload = json.dumps([{"input": "1", "reference": "1"}]).encode()
            client.post(
                f"/api/datasets/{ds['id']}/import",
                headers=h,
                files={"file": ("qa.json", payload, "application/json")},
            )
            bad = client.post(f"/api/datasets/{ds['id']}/publish", headers=h)
            self.assertEqual(bad.status_code, 400, bad.text)
            q = client.post("/api/quality/run", headers=h, params={"dataset_id": ds["id"]})
            self.assertEqual(q.status_code, 200, q.text)
            if q.json().get("status") == "passed":
                ok = client.post(f"/api/datasets/{ds['id']}/publish", headers=h)
                self.assertEqual(ok.status_code, 200, ok.text)


if __name__ == "__main__":
    unittest.main()
