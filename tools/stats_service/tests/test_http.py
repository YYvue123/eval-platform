from __future__ import annotations

import json
import subprocess
import sys
from unittest import TestCase

from fastapi.testclient import TestClient

from tools.stats_service.app import app
from tools.stats_service.mcp_protocol import PROTOCOL_VERSION


def _rpc(method: str, params: dict | None = None, request_id: int = 1) -> dict:
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def _sse_events(body: str) -> list[dict]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = {}
        for line in block.splitlines():
            name, value = line.split(":", 1)
            fields[name] = value.lstrip()
        fields["data"] = json.loads(fields["data"])
        events.append(fields)
    return events


class HttpApiTest(TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _initialize(self) -> str:
        response = self.client.post(
            "/mcp",
            json=_rpc(
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "tests", "version": "1"},
                },
            ),
        )
        self.assertEqual(response.status_code, 200)
        session_id = response.headers.get("mcp-session-id")
        self.assertTrue(session_id)
        return session_id

    def test_health_identifies_service_and_status(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"service": "stats-service", "status": "ok"}
        )

    def test_stats_accepts_platform_envelope_and_converts_units(self):
        response = self.client.post(
            "/v1/stats",
            json={
                "body": {
                    "parameters": {
                        "values": [{"value": 100, "unit": "cm"}],
                        "target_unit": "m",
                    }
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["result"]["converted"], [1.0])
        self.assertEqual(payload["result"]["unit"], "m")

    def test_parse_accepts_bare_parameters(self):
        response = self.client.post("/v1/parse", json={"text": "长 12 cm"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "success",
                "result": [{"value": 12.0, "unit": "cm"}],
            },
        )

    def test_invalid_input_is_business_error_over_http_200(self):
        response = self.client.post("/v1/stats", json={"values": []})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_INPUT")
        self.assertIn("空", payload["error"]["message"])

    def test_initialize_returns_negotiation_and_session_header(self):
        response = self.client.post(
            "/mcp",
            json=_rpc(
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "tests", "version": "1"},
                },
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers.get("mcp-session-id"))
        result = response.json()["result"]
        self.assertEqual(result["protocolVersion"], PROTOCOL_VERSION)
        self.assertTrue(result["capabilities"]["tools"]["listChanged"])
        self.assertEqual(result["serverInfo"]["name"], "stats-service")

    def test_initialized_notification_has_no_json_rpc_response(self):
        session_id = self._initialize()
        response = self.client.post(
            "/mcp",
            headers={"Mcp-Session-Id": session_id},
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")

    def test_non_initialize_requires_valid_session(self):
        response = self.client.post("/mcp", json=_rpc("tools/list", {}))
        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            "/mcp",
            headers={"Mcp-Session-Id": "missing"},
            json=_rpc("tools/list", {}),
        )
        self.assertEqual(response.status_code, 404)

    def test_tools_list_uses_two_single_tool_pages(self):
        session_id = self._initialize()
        first = self.client.post(
            "/mcp",
            headers={"Mcp-Session-Id": session_id},
            json=_rpc("tools/list", {}, 2),
        ).json()["result"]
        second = self.client.post(
            "/mcp",
            headers={"Mcp-Session-Id": session_id},
            json=_rpc("tools/list", {"cursor": "1"}, 3),
        ).json()["result"]
        self.assertEqual(len(first["tools"]), 1)
        self.assertEqual(first["nextCursor"], "1")
        self.assertEqual(len(second["tools"]), 1)
        self.assertNotIn("nextCursor", second)
        self.assertEqual(
            {first["tools"][0]["name"], second["tools"][0]["name"]},
            {"parse_measurements", "compute_stats"},
        )

    def test_tool_business_error_is_json_rpc_result(self):
        session_id = self._initialize()
        response = self.client.post(
            "/mcp",
            headers={"Mcp-Session-Id": session_id},
            json=_rpc(
                "tools/call",
                {"name": "compute_stats", "arguments": {"values": []}},
                4,
            ),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("error", payload)
        self.assertTrue(payload["result"]["isError"])
        self.assertIn("空", payload["result"]["content"][0]["text"])

    def test_unknown_method_returns_method_not_found(self):
        session_id = self._initialize()
        payload = self.client.post(
            "/mcp",
            headers={"Mcp-Session-Id": session_id},
            json=_rpc("unknown/method", {}, 5),
        ).json()
        self.assertEqual(payload["error"]["code"], -32601)

    def test_stream_request_returns_sse_json_rpc_response(self):
        session_id = self._initialize()
        response = self.client.post(
            "/mcp",
            headers={
                "Mcp-Session-Id": session_id,
                "Accept": "application/json, text/event-stream",
            },
            json=_rpc("tools/list", {"_meta": {"stream": True}}, 6),
        )
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        events = _sse_events(response.text)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "message")
        self.assertEqual(events[0]["data"]["id"], 6)

    def test_list_changed_notification_precedes_response(self):
        session_id = self._initialize()
        response = self.client.post(
            "/mcp",
            headers={
                "Mcp-Session-Id": session_id,
                "Accept": "text/event-stream",
            },
            json=_rpc(
                "tools/list",
                {
                    "_meta": {
                        "stream": True,
                        "announce_list_changed": True,
                    }
                },
                7,
            ),
        )
        events = _sse_events(response.text)
        self.assertEqual(len(events), 2)
        self.assertEqual(
            events[0]["data"]["method"], "notifications/tools/list_changed"
        )
        self.assertEqual(events[1]["data"]["id"], 7)
        self.assertLess(int(events[0]["id"]), int(events[1]["id"]))

    def test_drop_then_get_with_last_event_id_recovers_response(self):
        session_id = self._initialize()
        dropped = self.client.post(
            "/mcp",
            headers={
                "Mcp-Session-Id": session_id,
                "Accept": "text/event-stream",
            },
            json=_rpc(
                "tools/list",
                {"_meta": {"stream": True, "drop_before_response": True}},
                8,
            ),
        )
        dropped_events = _sse_events(dropped.text)
        self.assertEqual(len(dropped_events), 1)
        self.assertIn("method", dropped_events[0]["data"])
        self.assertNotIn("id", dropped_events[0]["data"])

        recovered = self.client.get(
            "/mcp",
            headers={
                "Mcp-Session-Id": session_id,
                "Last-Event-ID": dropped_events[0]["id"],
                "Accept": "text/event-stream",
            },
        )
        self.assertEqual(recovered.status_code, 200)
        recovered_events = _sse_events(recovered.text)
        self.assertEqual(len(recovered_events), 1)
        self.assertEqual(recovered_events[0]["data"]["id"], 8)

    def test_delete_invalidates_session(self):
        session_id = self._initialize()
        deleted = self.client.delete(
            "/mcp", headers={"Mcp-Session-Id": session_id}
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(deleted.content, b"")
        rejected = self.client.post(
            "/mcp",
            headers={"Mcp-Session-Id": session_id},
            json=_rpc("tools/list", {}, 9),
        )
        self.assertEqual(rejected.status_code, 404)


class StdioServerTest(TestCase):
    def test_stdio_lifecycle_and_parse_error(self):
        messages = [
            _rpc(
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "tests", "version": "1"},
                },
                10,
            ),
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
            _rpc("tools/list", {}, 11),
            _rpc(
                "tools/call",
                {
                    "name": "parse_measurements",
                    "arguments": {"text": "1 m"},
                },
                12,
            ),
        ]
        stdin = "\n".join(json.dumps(item) for item in messages)
        stdin += "\n{not-json}\n"
        completed = subprocess.run(
            [sys.executable, "-m", "tools.stats_service.stdio_server"],
            input=stdin,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = [
            json.loads(line) for line in completed.stdout.splitlines() if line.strip()
        ]
        self.assertEqual([item.get("id") for item in output], [10, 11, 12, None])
        self.assertEqual(output[0]["result"]["protocolVersion"], PROTOCOL_VERSION)
        self.assertEqual(output[1]["result"]["tools"][0]["name"], "parse_measurements")
        self.assertFalse(output[2]["result"]["isError"])
        self.assertEqual(output[3]["error"]["code"], -32700)
