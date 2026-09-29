from __future__ import annotations

import json

import httpx

from app.services.mcp.errors import McpError
from app.services.side_effect_policy import assert_egress_allowed
from app.services.tls_channel import httpx_tls_kwargs

MAX_BODY_BYTES = 1024 * 1024


def parse_sse(lines: list[str]) -> list[dict]:
    events = []
    current = {"event": "message", "data": [], "id": ""}
    for line in lines:
        if line == "":
            if current["data"]:
                events.append({
                    "event": current["event"],
                    "id": current["id"],
                    "data": "\n".join(current["data"]),
                })
            current = {"event": "message", "data": [], "id": ""}
        elif line.startswith("data:"):
            current["data"].append(line[5:].lstrip())
        elif line.startswith("event:"):
            current["event"] = line[6:].strip()
        elif line.startswith("id:"):
            current["id"] = line[3:].strip()
    return events


class HttpTransport:
    def __init__(
        self,
        endpoint: str,
        *,
        auth_token: str | None = None,
        timeout: int = 30,
        channel: str = "https",
        manifest: dict | None = None,
    ):
        self.endpoint = endpoint
        self.auth_token = auth_token
        self.timeout = timeout
        self.channel = channel
        self.manifest = manifest
        self.session_id: str | None = None
        self.protocol_version: str | None = None
        self.last_event_id: str = ""
        self._stream_event_id: str = ""
        self.notifications: list[dict] = []
        self._client = httpx.AsyncClient(
            timeout=timeout,
            **httpx_tls_kwargs(channel),
        )
        assert_egress_allowed(endpoint, manifest)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.protocol_version:
            headers["MCP-Protocol-Version"] = self.protocol_version
        return headers

    def _capture_session(self, response: httpx.Response) -> None:
        sid = response.headers.get("mcp-session-id") or response.headers.get("Mcp-Session-Id")
        if sid:
            self.session_id = sid

    def _raise_status(self, status: int, detail: str = "") -> None:
        message = detail or f"HTTP {status}"
        if status in (401, 403):
            raise McpError("MCP_AUTH_FAILED", message)
        if status == 404 and self.session_id:
            raise McpError("MCP_SESSION_EXPIRED", message)
        raise McpError("MCP_TRANSPORT_ERROR", message)

    def _rpc_error(self, payload: dict) -> None:
        err = payload.get("error")
        if not err:
            return
        if isinstance(err, dict):
            message = str(err.get("message") or err)
        else:
            message = str(err)
        raise McpError("MCP_PROTOCOL_ERROR", message)

    def _parse_event_data(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise McpError("MCP_TRANSPORT_ERROR", f"invalid SSE JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise McpError("MCP_TRANSPORT_ERROR", "SSE data must be a JSON object")
        return data

    def _ingest_event(self, event: dict, request_id) -> dict | None:
        event_id = event.get("id") or ""
        if event_id:
            self.last_event_id = event_id
            self._stream_event_id = event_id
        data = self._parse_event_data(event.get("data") or "")
        if request_id is not None and data.get("id") == request_id:
            self._rpc_error(data)
            return data
        if data.get("method"):
            self.notifications.append(data)
        return None

    async def _read_limited(self, response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > MAX_BODY_BYTES:
                raise McpError("MCP_TRANSPORT_ERROR", "response body exceeds 1 MiB")
            chunks.append(chunk)
        return b"".join(chunks)

    async def _read_sse(self, response: httpx.Response, request_id) -> dict | None:
        current = {"event": "message", "data": [], "id": ""}
        total = 0
        matched = None

        async def feed(line: str) -> dict | None:
            nonlocal current
            if line == "":
                if current["data"]:
                    event = {
                        "event": current["event"],
                        "id": current["id"],
                        "data": "\n".join(current["data"]),
                    }
                    current = {"event": "message", "data": [], "id": ""}
                    return self._ingest_event(event, request_id)
                current = {"event": "message", "data": [], "id": ""}
                return None
            if line.startswith("data:"):
                current["data"].append(line[5:].lstrip())
            elif line.startswith("event:"):
                current["event"] = line[6:].strip()
            elif line.startswith("id:"):
                current["id"] = line[3:].strip()
            return None

        async for line in response.aiter_lines():
            total += len(line.encode("utf-8")) + 1
            if total > MAX_BODY_BYTES:
                raise McpError("MCP_TRANSPORT_ERROR", "response body exceeds 1 MiB")
            found = await feed(line)
            if found is not None:
                matched = found
                break
        return matched

    async def _resume_once(self, request_id) -> dict | None:
        if not self._stream_event_id:
            return None
        headers = self._headers()
        headers["Last-Event-ID"] = self._stream_event_id
        try:
            async with self._client.stream("GET", self.endpoint, headers=headers) as response:
                self._capture_session(response)
                if response.status_code >= 400:
                    self._raise_status(response.status_code)
                return await self._read_sse(response, request_id)
        except McpError:
            raise
        except httpx.TimeoutException as exc:
            raise McpError("MCP_TIMEOUT", "MCP GET resume timed out") from exc
        except httpx.HTTPError as exc:
            raise McpError("MCP_TRANSPORT_ERROR", str(exc) or "MCP GET failed") from exc

    async def send(self, message: dict, *, notification: bool = False) -> dict | None:
        assert_egress_allowed(self.endpoint, self.manifest)
        request_id = None if notification else message.get("id")
        self._stream_event_id = ""
        matched = None
        try:
            async with self._client.stream(
                "POST",
                self.endpoint,
                json=message,
                headers=self._headers(),
            ) as response:
                self._capture_session(response)
                if response.status_code >= 400:
                    self._raise_status(response.status_code)
                content_type = (response.headers.get("content-type") or "").lower()
                if "text/event-stream" in content_type:
                    matched = await self._read_sse(response, request_id)
                elif notification or response.status_code == 204:
                    await response.aread()
                    return None
                else:
                    raw = await self._read_limited(response)
                    if not raw:
                        raise McpError("MCP_TRANSPORT_ERROR", "empty MCP response")
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise McpError("MCP_TRANSPORT_ERROR", "invalid JSON response") from exc
                    if not isinstance(payload, dict):
                        raise McpError("MCP_TRANSPORT_ERROR", "MCP response is not an object")
                    self._rpc_error(payload)
                    return payload
        except McpError:
            raise
        except httpx.TimeoutException as exc:
            raise McpError("MCP_TIMEOUT", "MCP request timed out") from exc
        except httpx.HTTPError as exc:
            raise McpError("MCP_TRANSPORT_ERROR", str(exc) or "MCP HTTP failed") from exc

        if notification:
            return None
        if matched is not None:
            return matched
        if self._stream_event_id:
            resumed = await self._resume_once(request_id)
            if resumed is not None:
                return resumed
        raise McpError("MCP_TRANSPORT_ERROR", "SSE stream ended without a JSON-RPC response")

    async def close(self) -> None:
        try:
            if self.session_id:
                try:
                    response = await self._client.delete(self.endpoint, headers=self._headers())
                    if response.status_code not in (200, 204, 405):
                        self._raise_status(response.status_code)
                except McpError:
                    raise
                except httpx.TimeoutException as exc:
                    raise McpError("MCP_TIMEOUT", "MCP session close timed out") from exc
                except httpx.HTTPError as exc:
                    raise McpError("MCP_TRANSPORT_ERROR", str(exc) or "MCP DELETE failed") from exc
        finally:
            await self._client.aclose()
