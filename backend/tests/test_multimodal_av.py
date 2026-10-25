"""Isolated audio/video contracts. Scripted transports never count as real admission."""
from tests import isolated_env  # noqa: F401
import base64
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from tests.media_fixtures import audio_entry, video_entry
from app.services.multimodal import media_of, messages_for, measurement, validate_compatibility, request_options
from app.services.model_client import _invoke_once


def item(media, **extra):
    return NS(extended_content=json.dumps({"media": media, **extra}))


class AVContracts(unittest.TestCase):
    def test_audio_bytes_segments_and_openai_block(self):
        media = media_of(item([audio_entry()]))
        self.assertEqual(media[0]["duration_seconds"], 1)
        self.assertEqual(media[0]["segments"][0]["end"], .5)
        block = messages_for("listen", media)[0]["content"][1]
        self.assertEqual(block["type"], "input_audio")
        self.assertEqual(block["input_audio"]["format"], "wav")
        self.assertEqual(measurement(media)["input_modality"], "audio")
        with self.assertRaises(ValueError):
            validate_compatibility(NS(support_modal="text,image"), item([audio_entry()]))

    def test_video_actual_frames_are_timestamped_and_forgery_rebuilt(self):
        original = video_entry()
        media = media_of(item([{**original, "frames": [{"data_url": "forged"}], "has_audio": True}]))
        self.assertFalse(media[0]["has_audio"])
        self.assertEqual([f["timestamp_seconds"] for f in media[0]["frames"]], [0, 1.5])
        self.assertNotEqual(media[0]["frames"][0]["sha256"], media[0]["frames"][1]["sha256"])
        self.assertTrue(validate_compatibility(NS(support_modal="text,image"), item([original])))
        self.assertIn("非连续", measurement(media)["measurement_scope"])
        self.assertIn("continuous_video", measurement(media)["unmeasured"])

    def test_low_fps_records_actual_instead_of_invented_frame_time(self):
        media = media_of(item([video_entry(fps=1)]))
        self.assertEqual(media[0]["frames"][1]["requested_timestamp_seconds"], 1.5)
        self.assertEqual(media[0]["frames"][1]["timestamp_seconds"], 1.0)

    def test_video_audio_cannot_be_silently_dropped(self):
        source = video_entry(True)
        media = media_of(item([source]))
        self.assertTrue(media[0]["has_audio"])
        self.assertTrue(media[0]["audio_track"]["data_url"].startswith("data:audio/wav"))
        blocks = messages_for("inspect", media)[0]["content"]
        self.assertIn("input_audio", [b["type"] for b in blocks])
        with self.assertRaises(ValueError):
            validate_compatibility(NS(support_modal="text,image"), item([source]))
        self.assertTrue(validate_compatibility(NS(support_modal="text,image,audio"), item([source])))

    def test_native_video_requires_explicit_video_capability(self):
        source = {**video_entry(), "video_mode": "native"}
        with self.assertRaises(ValueError):
            validate_compatibility(NS(support_modal="text,image"), item([source]))
        media = validate_compatibility(NS(support_modal="text,video"), item([source]))
        self.assertEqual(messages_for("watch", media)[0]["content"][1]["type"], "video_url")

    def test_time_segments_and_sampling_outside_clip_rejected(self):
        for entry in [{**audio_entry(), "segments": [{"start": 0, "end": 2}]},
                      {**video_entry(), "frame_timestamps": [3]},
                      {**audio_entry(), "data_url": audio_entry()["data_url"].replace("audio/wav", "audio/mp3")}]:
            with self.assertRaises(ValueError):
                media_of(item([entry]))

    def test_audio_output_requires_target_output_and_judge_input_capability(self):
        row = item([], response_modalities=["text", "audio"], audio_output={"voice": "alloy", "format": "wav"})
        with self.assertRaises(ValueError):
            validate_compatibility(NS(support_modal="text"), row)
        self.assertEqual(request_options(row)["audio"]["format"], "wav")
        self.assertEqual(validate_compatibility(NS(support_modal='{"input":["text"],"output":["text","audio"]}'), row), [])
        with self.assertRaises(ValueError):
            validate_compatibility(NS(support_modal="text"), row, judge=True)
        self.assertEqual(validate_compatibility(NS(support_modal="text,audio"), row, judge=True), [])


class AudioTransport(unittest.IsolatedAsyncioTestCase):
    async def test_skill_explicitly_forwards_original_media(self):
        from app.services.skill_runtime import run_skill
        source = audio_entry()
        manifest = {"skill": {"execution_type": "workflow", "chain": [{"step_id": "inspect",
            "resource_id": "builtin/media_inspect", "input": {"media": {"$ref": "$input.media"}}}]}}
        observed = []
        async def invoke(step, rid, payload):
            observed.append(payload)
            return {"body": {"status": "success", "result": {"media": [{"modality": "audio"}], "measurement_scope": "inspection_only"}}}
        result = await run_skill(manifest, {"media": [source]}, step_invoker=invoke)
        from app.services.judge_options import unwrap_judge
        with self.assertRaises(RuntimeError):
            unwrap_judge(result)
        self.assertEqual(observed[0]["media"][0]["data_url"], source["data_url"])

    async def test_requested_audio_preserved_and_missing_audio_fails(self):
        model = NS(id=1, api_url="https://example.invalid", name="audio", served_model_name="audio", api_key="",
                   timeout=1, retry_count=0, channel_type="https", request_method="POST", consecutive_fail=0)
        encoded = audio_entry()["data_url"].split(",", 1)[1]
        for present in (True, False):
            content = {"content": None, "audio": {"data": encoded, "transcript": "measured transcript"}} if present else {"content": "text only"}
            response = httpx.Response(200, json={"choices": [{"message": content}], "usage": {"total_tokens": 2}}, request=httpx.Request("POST", model.api_url))
            client = NS(request=AsyncMock(return_value=response))
            cm = AsyncMock()
            cm.__aenter__.return_value = client
            with patch("app.services.model_client.httpx.AsyncClient", return_value=cm):
                if not present:
                    with self.assertRaises(RuntimeError):
                        await _invoke_once(model, "speak", response_modalities=["text", "audio"], audio={"voice": "alloy", "format": "wav"})
                else:
                    result = await _invoke_once(model, "speak", response_modalities=["text", "audio"], audio={"voice": "alloy", "format": "wav"})
                    self.assertEqual(result["output"], "measured transcript")
                    self.assertEqual(result["output_audio"]["modality"], "audio")
                    self.assertEqual(client.request.await_args.kwargs["json"]["modalities"], ["text", "audio"])


class AVGatewayAgentTests(unittest.TestCase):
    def test_inspector_has_no_score_and_agent_checks_audio_capability(self):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            auth = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()
            headers = {"Authorization": "Bearer " + auth["access_token"]}
            source = audio_entry()
            inspected = c.post("/api/resources/invoke", headers=headers, json={"resource_id": "builtin/media_inspect", "body": {"media": [source]}})
            self.assertEqual(inspected.status_code, 200, inspected.text)
            result = inspected.json()["body"]["result"]
            self.assertNotIn("score", result)
            self.assertNotIn("passed", result)
            self.assertEqual(result["media"][0]["duration_seconds"], 1)
            ds = c.post("/api/datasets", headers=headers, json={"name": "isolated-audio-gate"}).json()
            imported = c.post(f"/api/datasets/{ds['id']}/import", headers=headers,
                files={"file": ("audio.json", json.dumps([{"input": "listen", "reference": "silence", "media": [source]}]).encode(), "application/json")})
            self.assertEqual(imported.status_code, 200, imported.text)
            model = c.post("/api/models", headers=headers, json={"name": "isolated-text-target", "support_modal": "text"}).json()
            session = c.post("/api/agents/sessions", headers=headers, json={"requirement": "音频评测", "objective": "检查媒体匹配", "auto_plan": False}).json()
            blocked = c.post(f"/api/agents/sessions/{session['id']}/clarify", headers=headers,
                json={"dataset_id": ds["id"], "model_id": model["id"], "trial_run": True})
            self.assertEqual(blocked.status_code, 200, blocked.text)
            self.assertFalse(blocked.json()["plan"]["ready"])
            self.assertTrue(any("audio" in e for e in blocked.json()["plan"]["validation_errors"]))
            c.put(f"/api/models/{model['id']}", headers=headers, json={"support_modal": "text,audio"})
            allowed = c.post(f"/api/agents/sessions/{session['id']}/clarify", headers=headers, json={"model_id": model["id"]})
            self.assertEqual(allowed.status_code, 200, allowed.text)
            self.assertEqual(allowed.json()["plan"]["media_summary"]["input_modalities"], {"audio": 1})
            # Still no real audio execution or scoring has taken place.
            self.assertIsNone(allowed.json()["task_id"])
