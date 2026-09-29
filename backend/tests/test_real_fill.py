from tests import isolated_env  # noqa: F401

import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from tests.isolated_env import assert_isolated_database

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.followup_helpers import stats_service
from tools.real_fill.client import FillClient
from tools.real_fill.scenarios import (
    agent_events_count_as_tool_loop,
    real01_accounts,
    real02_dataset,
    real03_models,
    real04_tools,
    real05_mcp,
    real06_agent,
    real07_formal_task,
    real08_prompts,
    real09_safety,
    real10_leaderboard,
    real11_shadow,
    real12_ops,
)


class RealFillTests(unittest.TestCase):
    def test_isolated_url_is_not_business_db(self):
        url = os.environ["DATABASE_URL"]
        db_path = assert_isolated_database(url)
        self.assertNotEqual(db_path.name, "eval_platform.db")

    def test_fill_client_login_admin(self):
        with TestClient(app) as raw:
            client = FillClient(raw)
            client.login("admin", "admin123")
            me = client.request("GET", "/api/users/me")
            self.assertEqual(me.status_code, 200, me.text)
            self.assertEqual(me.json()["username"], "admin")

    def test_real01_viewer_cannot_register(self):
        with TestClient(app) as raw:
            admin = FillClient(raw)
            viewer = FillClient(raw)
            result = real01_accounts(admin, viewer)
            self.assertEqual(result["result"], "pass")
            self.assertEqual(result["admin_login_status"], 200)
            self.assertIn(result["viewer_denied_status"], (401, 403))
            self.assertNotEqual(result["viewer_denied_status"], 200)

    def test_real02_dataset_import_returns_ids(self):
        with TestClient(app) as raw:
            client = FillClient(raw)
            result = real02_dataset(client)
            self.assertIsInstance(result["dataset_id"], int)
            self.assertIsInstance(result["version_id"], int)
            self.assertGreater(result["dataset_id"], 0)
            self.assertGreater(result["version_id"], 0)
            detail = client.request("GET", f"/api/datasets/{result['dataset_id']}")
            self.assertEqual(detail.status_code, 200, detail.text)
            self.assertIn("AI 生成确定性题集", detail.json()["description"])
            items = client.request(
                "GET",
                f"/api/datasets/{result['dataset_id']}/items",
                params={"version_id": result["version_id"]},
            )
            self.assertEqual(items.status_code, 200, items.text)
            self.assertEqual(items.json()["total"], 4)

    def test_real04_tools_parse_three_inputs_one_failed(self):
        with TestClient(app) as raw:
            client = FillClient(raw)
            with stats_service() as base_url:
                result = real04_tools(client, base_url)
            self.assertEqual(result["result"], "pass")
            parse_rid = result["parse_resource_id"]
            stats_rid = result["stats_resource_id"]
            self.assertTrue(parse_rid)
            self.assertTrue(stats_rid)
            self.assertNotEqual(parse_rid, stats_rid)
            cids = result["parse_correlation_ids"]
            self.assertEqual(len(cids), 3)
            self.assertEqual(len(set(cids)), 3)
            self.assertTrue(result["failed_correlation_id"])
            self.assertIn(result["failed_correlation_id"], cids)
            parse_detail = client.request("GET", f"/api/resources/{parse_rid}")
            stats_detail = client.request("GET", f"/api/resources/{stats_rid}")
            self.assertEqual(parse_detail.status_code, 200, parse_detail.text)
            self.assertEqual(stats_detail.status_code, 200, stats_detail.text)
            history = client.request("GET", f"/api/resources/calls/{parse_rid}")
            self.assertEqual(history.status_code, 200, history.text)
            items = history.json()["items"]
            by_cid = {item["correlation_id"]: item for item in items}
            for cid in cids:
                self.assertIn(cid, by_cid)
            self.assertEqual(by_cid[result["failed_correlation_id"]]["status"], "failed")
            successes = [
                item for cid, item in by_cid.items() if cid in cids and item["status"] == "success"
            ]
            self.assertEqual(len(successes), 2)
            skill_rid = result["skill_resource_id"]
            self.assertTrue(skill_rid)
            skill_detail = client.request("GET", f"/api/resources/{skill_rid}")
            self.assertEqual(skill_detail.status_code, 200, skill_detail.text)
            self.assertEqual(skill_detail.json()["resource_type"], "skill")
            skill_history = client.request("GET", f"/api/resources/calls/{skill_rid}")
            self.assertEqual(skill_history.status_code, 200, skill_history.text)
            skill_items = skill_history.json()["items"]
            self.assertTrue(skill_items)
            self.assertEqual(skill_items[0]["status"], "success")

    def test_real05_mcp_tools_call_success_and_empty_args_failed(self):
        with TestClient(app) as raw:
            client = FillClient(raw)
            with stats_service() as base_url:
                result = real05_mcp(client, base_url)
            self.assertEqual(result["result"], "pass")
            self.assertTrue(result["success_ok"])
            self.assertFalse(result["empty_args_ok"])
            rid = result.get("mcp_resource_id")
            if rid:
                detail = client.request("GET", f"/api/resources/{rid}")
                self.assertEqual(detail.status_code, 200, detail.text)
                self.assertEqual(detail.json()["resource_type"], "mcp")
                history = client.request("GET", f"/api/resources/calls/{rid}")
                self.assertEqual(history.status_code, 200, history.text)
                statuses = {item["status"] for item in history.json()["items"]}
                self.assertIn("success", statuses)
                self.assertIn("failed", statuses)

    def test_real03_06_07_blocked_without_l3_url(self):
        class ForbiddenClient:
            def login(self, *args, **kwargs):
                raise AssertionError("blocked path must not login or start stats_service")

            def request(self, *args, **kwargs):
                raise AssertionError("blocked path must not call APIs")

        client = ForbiddenClient()

        def assert_blocked(fn, scenario, *args, **kwargs):
            out = fn(*args, **kwargs)
            self.assertEqual(out["result"], "blocked")
            self.assertEqual(out["scenario"], scenario)
            self.assertIn("missing L3_MODEL_API_URL", out["blocking_reason"])
            self.assertNotIn("api_url", out)
            self.assertNotIn("api_key", out)

        with patch.dict(os.environ, clear=False):
            os.environ.pop("L3_MODEL_API_URL", None)
            assert_blocked(real03_models, "REAL03", client)
            assert_blocked(real06_agent, "REAL06", client, parse_resource_id="demo/parse_ui")
            assert_blocked(
                real07_formal_task,
                "REAL07",
                client,
                dataset_id=1,
                version_id=1,
                model_id=1,
            )
            assert_blocked(real08_prompts, "REAL08", client, dataset_id=1)

        with patch.dict(os.environ, {"L3_MODEL_API_URL": ""}, clear=False):
            assert_blocked(real03_models, "REAL03", client)
            assert_blocked(real06_agent, "REAL06", client)
            assert_blocked(
                real07_formal_task,
                "REAL07",
                client,
                dataset_id=1,
                version_id=1,
                model_id=1,
            )
            assert_blocked(real08_prompts, "REAL08", client, dataset_id=1)

    def test_agent_events_count_as_tool_loop(self):
        self.assertFalse(agent_events_count_as_tool_loop(["tool.rejected"]))
        self.assertFalse(agent_events_count_as_tool_loop(["tool.failed"]))
        self.assertFalse(agent_events_count_as_tool_loop(["tool.selected"]))
        self.assertFalse(agent_events_count_as_tool_loop(["tool.rejected", "tool.failed"]))
        self.assertFalse(agent_events_count_as_tool_loop([]))
        self.assertTrue(agent_events_count_as_tool_loop(["tool.observed"]))
        self.assertTrue(agent_events_count_as_tool_loop(["run.started", "tool.observed"]))

    def test_real06_missing_parse_resource_blocked(self):
        with TestClient(app) as raw:
            client = FillClient(raw)
            with patch(
                "tools.real_fill.scenarios._l3_url_present",
                return_value=True,
            ):
                out = real06_agent(client)
            self.assertEqual(out["result"], "blocked")
            self.assertEqual(out["scenario"], "REAL06")
            self.assertIn("parse", out["blocking_reason"].lower())
            self.assertNotIn("api_url", out)
            self.assertNotIn("api_key", out)

    def test_real06_pass_on_invoke_success_without_tool_observed(self):
        class _Resp:
            def __init__(self, status_code, payload=None):
                self.status_code = status_code
                self._payload = payload or {}

            def json(self):
                return self._payload

        class _FakeClient:
            def login(self, *args, **kwargs):
                return None

            def request(self, method, path, **kwargs):
                if path == "/api/resources/invoke":
                    return _Resp(200, {"body": {"status": "success"}})
                if path == "/api/models":
                    return _Resp(200, {"id": 9, "api_url": "https://l3.example/v1"})
                if path == "/api/agents/sessions":
                    return _Resp(200, {"id": "sess-1"})
                if path.endswith("/confirm"):
                    return _Resp(400, {})
                if path.endswith("/runs"):
                    return _Resp(200, {"id": "run-1"})
                if path.endswith("/events"):
                    return _Resp(200, {"items": [{"type": "tool.rejected"}]})
                raise AssertionError(f"unexpected {method} {path}")

        with patch(
            "tools.real_fill.scenarios._l3_url_present",
            return_value=True,
        ), patch.dict(os.environ, {"L3_MODEL_API_URL": "https://l3.example/v1"}, clear=False):
            out = real06_agent(_FakeClient(), parse_resource_id="demo/parse_ui")
        self.assertEqual(out["result"], "pass")
        self.assertEqual(out["confirm_status"], 400)
        self.assertEqual(out["run_id"], "run-1")
        self.assertTrue(out["parse_correlation_id"])
        self.assertFalse(out["agent_tool_observed"])
        self.assertNotIn("api_url", out)
        self.assertNotIn("api_key", out)

    def test_real06_invoke_failed_blocked(self):
        class _Resp:
            def __init__(self, status_code, payload=None):
                self.status_code = status_code
                self._payload = payload or {}

            def json(self):
                return self._payload

        class _FakeClient:
            def login(self, *args, **kwargs):
                return None

            def request(self, method, path, **kwargs):
                if path == "/api/resources/invoke":
                    return _Resp(200, {"body": {"status": "failed"}})
                if path == "/api/models":
                    return _Resp(200, {"id": 9, "api_url": "https://l3.example/v1"})
                if path == "/api/agents/sessions":
                    return _Resp(200, {"id": "sess-1"})
                if path.endswith("/confirm"):
                    return _Resp(200, {})
                if path.endswith("/runs"):
                    return _Resp(200, {"id": "run-1"})
                if path.endswith("/events"):
                    return _Resp(200, {"items": [{"type": "tool.observed"}]})
                raise AssertionError(f"unexpected {method} {path}")

        with patch(
            "tools.real_fill.scenarios._l3_url_present",
            return_value=True,
        ), patch.dict(os.environ, {"L3_MODEL_API_URL": "https://l3.example/v1"}, clear=False):
            out = real06_agent(_FakeClient(), parse_resource_id="demo/parse_ui")
        self.assertEqual(out["result"], "blocked")
        self.assertEqual(out["blocking_reason"], "tool_invoke_failed")
        self.assertFalse(out.get("agent_tool_observed") is True and out["result"] == "pass")

    def test_real06_empty_api_url_blocked(self):
        class _Resp:
            def __init__(self, status_code, payload=None):
                self.status_code = status_code
                self._payload = payload or {}

            def json(self):
                return self._payload

        class _FakeClient:
            def login(self, *args, **kwargs):
                return None

            def request(self, method, path, **kwargs):
                if path == "/api/resources/invoke":
                    return _Resp(200, {"body": {"status": "success"}})
                if path == "/api/models":
                    return _Resp(200, {"id": 9, "api_url": ""})
                if path == "/api/agents/sessions":
                    return _Resp(200, {"id": "sess-1"})
                if path.endswith("/confirm"):
                    return _Resp(200, {})
                if path.endswith("/runs"):
                    return _Resp(200, {"id": "run-1"})
                if path.endswith("/events"):
                    return _Resp(200, {"items": [{"type": "tool.observed"}]})
                raise AssertionError(f"unexpected {method} {path}")

        with patch(
            "tools.real_fill.scenarios._l3_url_present",
            return_value=True,
        ):
            out = real06_agent(_FakeClient(), parse_resource_id="demo/parse_ui")
        self.assertEqual(out["result"], "blocked")
        self.assertIn("api_url", out["blocking_reason"])
        self.assertNotEqual(out["result"], "pass")

    def test_empty_api_url_health_invoke_not_pass(self):
        with TestClient(app) as raw:
            client = FillClient(raw)
            client.login("admin", "admin123")
            created = client.request(
                "POST",
                "/api/models",
                json={"name": f"real03-empty-{uuid.uuid4().hex[:8]}", "api_url": ""},
            )
            self.assertEqual(created.status_code, 200, created.text)
            model_id = created.json()["id"]
            health = client.request("POST", f"/api/models/{model_id}/health")
            self.assertEqual(health.status_code, 200, health.text)
            body = health.json()
            self.assertFalse(body.get("ok"))
            invoke = client.request(
                "POST",
                f"/api/models/{model_id}/invoke",
                json={"prompt": "ping"},
            )
            self.assertNotEqual(invoke.status_code, 200)
            self.assertIn(invoke.status_code, (400, 403, 422))
            self.assertIn("model_api_url_required", invoke.text)

    def test_real08_blocked_without_l3_url(self):
        class ForbiddenClient:
            def login(self, *args, **kwargs):
                raise AssertionError("REAL08 blocked path must not login")

            def request(self, *args, **kwargs):
                raise AssertionError("REAL08 blocked path must not call APIs")

        with patch.dict(os.environ, clear=False):
            os.environ.pop("L3_MODEL_API_URL", None)
            out = real08_prompts(ForbiddenClient(), dataset_id=1)
        self.assertEqual(out["result"], "blocked")
        self.assertEqual(out["scenario"], "REAL08")
        self.assertIn("missing L3_MODEL_API_URL", out["blocking_reason"])

    def test_real09_never_signed_and_skips_expert_paths(self):
        recorded: list[str] = []

        class _Resp:
            def __init__(self, status_code, payload=None):
                self.status_code = status_code
                self._payload = payload or {}

            def json(self):
                return self._payload

        class RecordingClient:
            def login(self, *args, **kwargs):
                return None

            def request(self, method, path, **kwargs):
                recorded.append(f"{method.upper()} {path}")
                lowered = path.lower()
                for needle in ("sign", "approve", "expert"):
                    if needle in lowered:
                        raise AssertionError(f"REAL09 must not call {path}")
                if path == "/api/safety/score":
                    return _Resp(200, {"sample_id": "risk-f-001", "signed": False})
                return _Resp(404, {})

        out = real09_safety(RecordingClient())
        self.assertIsNot(out.get("signed"), True)
        self.assertNotEqual(out.get("signed"), True)
        for entry in recorded:
            low = entry.lower()
            self.assertNotIn("/sign", low)
            self.assertNotIn("approve", low)
            self.assertNotIn("expert", low)

        with TestClient(app) as raw:
            live = real09_safety(FillClient(raw))
        self.assertIsNot(live.get("signed"), True)

    def test_real10_4xx_publish_is_pass(self):
        class _Resp:
            def __init__(self, status_code, payload=None, text=""):
                self.status_code = status_code
                self.text = text or str(payload or "")
                self._payload = payload or {}

            def json(self):
                return self._payload

        class PublishClient:
            def login(self, *args, **kwargs):
                return None

            def request(self, method, path, **kwargs):
                if path == "/api/leaderboard/releases/publish":
                    return _Resp(400, {"detail": "no qualifying formal result"})
                raise AssertionError(f"unexpected {method} {path}")

        out = real10_leaderboard(PublishClient())
        self.assertEqual(out["result"], "pass")
        self.assertEqual(out["scenario"], "REAL10")
        self.assertIn(out["publish_status"], range(400, 500))

    def test_real10_missing_publish_endpoint_blocked(self):
        class _Resp:
            def __init__(self, status_code):
                self.status_code = status_code
                self.text = "not found"
                self._payload = {}

            def json(self):
                return self._payload

        class MissingClient:
            def login(self, *args, **kwargs):
                return None

            def request(self, method, path, **kwargs):
                return _Resp(404)

        out = real10_leaderboard(MissingClient())
        self.assertEqual(out["result"], "blocked")
        self.assertIn("endpoint_missing", out["blocking_reason"])

    def test_real11_blocked_seven_day_window(self):
        class ForbiddenClient:
            def login(self, *args, **kwargs):
                raise AssertionError("REAL11 must not forge timestamps via API")

            def request(self, *args, **kwargs):
                raise AssertionError("REAL11 must not call shadow/promote")

        out = real11_shadow(ForbiddenClient())
        self.assertEqual(out["result"], "blocked")
        self.assertEqual(out["scenario"], "REAL11")
        reason = out["blocking_reason"]
        self.assertTrue("七天" in reason or "seven" in reason.lower())

    def test_real12_backup_200_isolated(self):
        with TestClient(app) as raw:
            client = FillClient(raw)
            result = real12_ops(client)
        self.assertEqual(result["backup_status"], 200)
        self.assertTrue(result.get("backup_path") or result.get("path"))
        self.assertTrue(result.get("backup_sha256") or result.get("sha256"))
        db_path = assert_isolated_database(os.environ["DATABASE_URL"])
        self.assertNotEqual(db_path.name, "eval_platform.db")
        backup_dir = Path(os.environ["BACKUP_DIR"]).resolve()
        self.assertTrue(str(backup_dir).replace("\\", "/").endswith("/tests/_isolated/backups") or "tests" in str(backup_dir))
        recorded_path = result.get("backup_path") or result.get("path")
        self.assertTrue(str(Path(recorded_path).resolve()).startswith(str(backup_dir)))

    def test_cli_missing_or_mismatch_fingerprint_exits_1_no_http(self):
        import tempfile
        from unittest.mock import patch

        from tools.cleanup_mock.fingerprint import target_fingerprint
        from tools.real_fill.cli import main

        d = Path(tempfile.mkdtemp())
        db = d / "cli.db"
        db.write_bytes(b"isolated-cli")
        recorded: list[str] = []

        class BoomClient:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def post(self, *args, **kwargs):
                recorded.append("post")
                raise AssertionError("fingerprint failure must not write remote")

            def get(self, *args, **kwargs):
                recorded.append("get")
                raise AssertionError("fingerprint failure must not write remote")

            def request(self, *args, **kwargs):
                recorded.append("request")
                raise AssertionError("fingerprint failure must not write remote")

        argv_base = [
            "--base-url",
            "http://127.0.0.1:9",
            "--db",
            str(db),
            "--only",
            "REAL01",
        ]
        with patch("httpx.Client", return_value=BoomClient()):
            missing = main(argv_base)
            mismatch = main(argv_base + ["--confirm-fingerprint", "sha256:" + ("0" * 64)])
        self.assertEqual(missing, 1)
        self.assertEqual(mismatch, 1)
        self.assertEqual(recorded, [])
        self.assertTrue(target_fingerprint(db).startswith("sha256:"))

    def test_cli_empty_only_dry_run_lists_scenarios(self):
        import io
        import tempfile
        from contextlib import redirect_stdout
        from unittest.mock import patch

        from tools.cleanup_mock.fingerprint import target_fingerprint
        from tools.real_fill.cli import main

        d = Path(tempfile.mkdtemp())
        db = d / "dry.db"
        db.write_bytes(b"dry-run")
        fp = target_fingerprint(db)
        buf = io.StringIO()
        with patch("httpx.Client") as mocked:
            mocked.side_effect = AssertionError("dry-run must not POST scenarios")
            with redirect_stdout(buf):
                code = main(
                    [
                        "--db",
                        str(db),
                        "--confirm-fingerprint",
                        fp,
                    ]
                )
        self.assertEqual(code, 0)
        text = buf.getvalue()
        for sid in (
            "REAL01",
            "REAL02",
            "REAL03",
            "REAL04",
            "REAL05",
            "REAL06",
            "REAL07",
            "REAL08",
            "REAL09",
            "REAL10",
            "REAL11",
            "REAL12",
        ):
            self.assertIn(sid, text)
        self.assertNotIn("admin123", text)

    def test_cli_dry_run_from_repo_root_subprocess(self):
        import subprocess
        import tempfile

        from tools.cleanup_mock.fingerprint import target_fingerprint

        d = Path(tempfile.mkdtemp())
        db = d / "root.db"
        db.write_bytes(b"repo-root")
        fp = target_fingerprint(db)
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.real_fill",
                "--db",
                str(db),
                "--confirm-fingerprint",
                fp,
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("REAL01", proc.stdout)
        self.assertIn("REAL12", proc.stdout)
        self.assertNotIn("admin123", proc.stdout + proc.stderr)

    def test_cli_matching_fingerprint_uses_httpx_not_testclient(self):
        import tempfile
        from unittest.mock import patch

        from tools.cleanup_mock.fingerprint import target_fingerprint
        from tools.real_fill.cli import main

        d = Path(tempfile.mkdtemp())
        db = d / "ok.db"
        db.write_bytes(b"match")
        fp = target_fingerprint(db)
        used = {"httpx": False, "testclient": False}

        class _Resp:
            def __init__(self, status_code, payload=None):
                self.status_code = status_code
                self.text = str(payload or "")
                self._payload = payload or {}

            def json(self):
                return self._payload

        class FakeHttpx:
            def __init__(self, *args, **kwargs):
                used["httpx"] = True

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def post(self, path, **kwargs):
                return self.request("POST", path, **kwargs)

            def get(self, path, **kwargs):
                return self.request("GET", path, **kwargs)

            def request(self, method, path, **kwargs):
                if path == "/api/auth/login":
                    return _Resp(200, {"access_token": "tok"})
                if path == "/api/safety/score":
                    return _Resp(200, {"sample_id": "risk-f-001"})
                return _Resp(404, {})

        class FakeTestClient:
            def __init__(self, *args, **kwargs):
                used["testclient"] = True
                raise AssertionError("CLI must use httpx against --base-url")

        with patch("httpx.Client", FakeHttpx), patch(
            "fastapi.testclient.TestClient", FakeTestClient
        ):
            code = main(
                [
                    "--base-url",
                    "http://127.0.0.1:8001",
                    "--db",
                    str(db),
                    "--confirm-fingerprint",
                    fp,
                    "--only",
                    "REAL09",
                ]
            )
        self.assertEqual(code, 0)
        self.assertTrue(used["httpx"])
        self.assertFalse(used["testclient"])

    def test_isolated_evidence_dump_json(self):
        import json

        from tests.isolated_env import _ROOT
        from tools.real_fill.cli import dump_isolated_evidence

        with TestClient(app) as raw:
            rows = dump_isolated_evidence(FillClient(raw), FillClient(raw))
        out = _ROOT / "real_fill_isolated_evidence.json"
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        ids = [row["scenario"] for row in rows]
        self.assertEqual(
            ids,
            [
                "REAL01",
                "REAL02",
                "REAL03",
                "REAL04",
                "REAL05",
                "REAL06",
                "REAL07",
                "REAL08",
                "REAL09",
                "REAL10",
                "REAL11",
                "REAL12",
            ],
        )
        for row in rows:
            self.assertIn(row["result"], ("pass", "fail", "blocked", "not_run"))
            self.assertNotIn("api_key", json.dumps(row))
            self.assertNotIn("admin123", json.dumps(row))
        db_path = assert_isolated_database(os.environ["DATABASE_URL"])
        self.assertNotEqual(db_path.name, "eval_platform.db")
        l3_set = bool((os.environ.get("L3_MODEL_API_URL") or "").strip())
        for sid in ("REAL03", "REAL06", "REAL07", "REAL08"):
            row = next(r for r in rows if r["scenario"] == sid)
            if not l3_set:
                self.assertEqual(row["result"], "blocked")
                self.assertIn("missing L3_MODEL_API_URL", row["blocking_reason"])
