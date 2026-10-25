"""Isolated scripted transport checks; not evidence of real model capability."""
from tests import isolated_env  # noqa: F401

import base64
import io
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.services.multimodal import media_of, messages_for, validate_compatibility
from app.services.dataset_parser import parse_bytes
from app.services.dataset_revision import content_checksum_for_items
from app.services.model_access import model_call_view
from app.services.safety_protocol import SafetyConfig, summarize


def image_entry():
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(buf, format="PNG")
    return {"modality": "image", "data_url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
            "regions": [{"label": "red", "box": [0, 0, 1, 1]}]}


def item(media):
    return NS(extended_content=json.dumps({"media": media}))


class MediaTests(unittest.TestCase):
    def test_frozen_bytes_regions_and_import(self):
        entry = image_entry()
        rows = parse_bytes("samples.json", json.dumps([{"input": "颜色?", "media": [entry]}]).encode())
        frozen = rows[0]["extended_content"]["media"]
        self.assertEqual(len(frozen[0]["sha256"]), 64)
        self.assertEqual(frozen[0]["regions"], entry["regions"])
        self.assertEqual(messages_for("颜色?", frozen)[0]["content"][1]["image_url"]["url"], entry["data_url"])

    def test_invalid_media_fails_closed(self):
        for entry in [{"modality": "audio"}, {"modality": "video"}, {**image_entry(), "data_url": "https://example.com/a.png"},
                      {**image_entry(), "sha256": "wrong"}, {**image_entry(), "data_url": "data:image/png;base64,YWJj"},
                      {**image_entry(), "regions": [{"box": [1, 0, 0, 1]}]}]:
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                media_of(item([entry]))

    def test_explicit_input_output_capabilities(self):
        for declaration in ["text", "multimodal", '{"input":["text","image"],"output":["audio"]}']:
            with self.assertRaises(ValueError):
                validate_compatibility(NS(support_modal=declaration), item([image_entry()]))
        self.assertTrue(validate_compatibility(NS(support_modal='{"input":["text","image"],"output":["text"]}'), item([image_entry()])))
        self.assertEqual(messages_for("text", []), [{"role": "user", "content": "text"}])

    def test_checksum_changes_for_media_and_annotations(self):
        row = {"item_no": 1, "input_content": "same", "extended_content": {"media": [image_entry()]}}
        first = content_checksum_for_items([row])
        row["extended_content"]["media"][0]["regions"][0]["label"] = "changed"
        self.assertNotEqual(first, content_checksum_for_items([row]))

    def test_summary_never_fills_unmeasured_audio(self):
        result = NS(execution_status="ok", score_status="scored", simulation=False, score=1, passed=True,
                    metrics_json=json.dumps({"protocol": "safety-protocol-v2", "dimension": "risk.privacy", "input_modality": "image"}))
        summary = summarize([result], SafetyConfig(dimension_weights={"risk.privacy": 1}))
        self.assertEqual(summary["modalities"]["image"]["count"], 1)
        self.assertIsNone(summary["modalities"]["audio"]["score"])

    def test_visual_leaderboard_requires_measured_image_input(self):
        from app.services.leaderboard_insights import category_of
        task = NS(industry="general", task_type="capability")
        dataset = NS(name="test", tags="[]")
        model = NS(support_modal="text,image")
        text_result = NS(execution_status="ok", score_status="scored", simulation=False, metrics_json="{}")
        self.assertEqual(category_of(task, dataset, model, [text_result]), "language")
        text_result.metrics_json = '{"input_modality":"image"}'
        self.assertEqual(category_of(task, dataset, model, [text_result]), "vision")


class SafetyMediaTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_judge_receives_original_image(self):
        from app.services.safety_protocol import judge_response
        entry = image_entry()
        model = NS(id=1, status="online", support_modal="text,image")
        db = NS(get=AsyncMock(return_value=model), commit=AsyncMock(), add=lambda x: None)
        config = SafetyConfig(judge_model_id=1, rule_weight=.5)
        sample = {"question": "color?", "dimension": "risk.privacy", "rubric": "protect",
                  "media": [entry], "required_any": ["red"]}
        with patch("app.services.model_access.get_access_for_version", AsyncMock(return_value=None)), patch(
            "app.services.judge_options.invoke_judge", AsyncMock(return_value={"score": 1, "metrics": {}})
        ), patch("app.services.model_client.invoke_model", AsyncMock(return_value={
            "output": '{"score":1,"reason":"image evidence agrees","needs_review":false}', "tokens": 1, "latency_ms": 1
        })) as invoke:
            await judge_response(db, NS(id=1, fencing_token=0), "red", sample, config)
        self.assertEqual(invoke.await_args.kwargs["messages"][0]["content"][1]["image_url"]["url"], entry["data_url"])

    async def test_followup_and_perspective_keep_original_image(self):
        from app.services.safety_execution import evaluate_sample
        media = image_entry()
        sample = item([media])
        sample.difficulty_level = "base"
        meta = json.loads(sample.extended_content)
        meta["safety"] = {"dimension": "risk.privacy", "rubric": "Do not disclose", "expected_behavior": "refuse",
                          "probes": {"hard": ["again"]}, "perspectives": [{"label": "context", "context": "test"}]}
        sample.extended_content = json.dumps(meta)
        task = NS(id=1, model_id=1, token_quota=0, fencing_token=0,
                  safety_config_json=SafetyConfig(max_turns=2, perspective_evaluation=True).model_dump_json())
        db = NS(commit=AsyncMock(), add=lambda x: None)
        judgment = ({"score": 1, "metrics": {}}, 0, False)
        with patch("app.services.safety_execution.judge_response", AsyncMock(return_value=judgment)), patch(
            "app.services.safety_execution.invoke_model", AsyncMock(return_value={"output": "refuse", "tokens": 1, "latency_ms": 1})
        ) as invoke:
            await evaluate_sample(db, task, sample, NS(), "question", "refuse", 0)
        self.assertEqual(invoke.await_count, 2)
        for call in invoke.await_args_list:
            self.assertEqual(call.kwargs["messages"][0]["content"][1]["image_url"]["url"], media["data_url"])


class MediaApiTests(unittest.TestCase):
    def test_creation_gates_and_versioned_attachment_revision(self):
        from fastapi.testclient import TestClient
        from app.main import app
        import uuid
        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            headers = {"Authorization": "Bearer " + login.json()["access_token"]}
            name = "isolated-image-" + uuid.uuid4().hex[:8]
            ds = client.post("/api/datasets", headers=headers, json={"name": name}).json()
            imported = client.post(f"/api/datasets/{ds['id']}/import", headers=headers,
                files={"file": ("images.json", json.dumps([{"input": "颜色?", "media": [image_entry()]}]).encode(), "application/json")})
            self.assertEqual(imported.status_code, 200, imported.text)
            model = client.post("/api/models", headers=headers, json={"name": name, "support_modal": "text"}).json()
            payload = {"name": name, "dataset_id": ds["id"], "model_id": model["id"], "trial_run": True}
            rejected = client.post("/api/tasks", headers=headers, json=payload)
            self.assertEqual(rejected.status_code, 400, rejected.text)
            self.assertIn("text,image", rejected.text)
            changed = client.put(f"/api/models/{model['id']}", headers=headers, json={"support_modal": "text,image"})
            self.assertEqual(changed.status_code, 200, changed.text)
            accepted = client.post("/api/tasks", headers=headers, json=payload)
            self.assertEqual(accepted.status_code, 200, accepted.text)
            # The old model snapshot remains text-only after updating the live declaration.
            rejected_old = client.post("/api/tasks", headers=headers, json={**payload, "model_version_id": model["current_version_id"]})
            self.assertEqual(rejected_old.status_code, 400, rejected_old.text)
            old = client.get(f"/api/datasets/{ds['id']}/items", headers=headers).json()["items"][0]
            extra = old["extended_content"]
            extra["media"][0]["regions"][0]["label"] = "revised annotation"
            revised = client.patch(f"/api/datasets/{ds['id']}/items/{old['id']}", headers=headers, json={"extended_content": extra})
            self.assertEqual(revised.status_code, 200, revised.text)
            self.assertNotEqual(revised.json()["version_id"], old["version_id"])
            historic = client.get(f"/api/datasets/{ds['id']}/items", headers=headers, params={"version_id": old["version_id"]}).json()["items"][0]
            self.assertEqual(historic["extended_content"]["media"][0]["regions"][0]["label"], "red")
            invalid = client.post(f"/api/datasets/{ds['id']}/import", headers=headers,
                files={"file": ("invalid.json", json.dumps([{"input": "audio", "media": [{"modality": "audio"}]}]).encode(), "application/json")})
            self.assertEqual(invalid.status_code, 400, invalid.text)

