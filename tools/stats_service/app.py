from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from tools.stats_service.core import compute_stats, parse_measurements
from tools.stats_service.mcp_protocol import dispatch

app = FastAPI(title="stats-service")

_sessions: dict[str, dict[str, Any]] = {}


def _parameters(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("请求体必须为对象")
    body = payload.get("body")
    if isinstance(body, dict) and "parameters" in body:
        parameters = body["parameters"]
    else:
        parameters = payload
    if not isinstance(parameters, dict):
        raise ValueError("parameters 必须为对象")
    return parameters


def _success(result: Any) -> dict:
    return {"status": "success", "result": result}


def _invalid_input(exc: Exception) -> dict:
    return {
        "status": "error",
        "error": {"code": "INVALID_INPUT", "message": str(exc)},
    }


def _event(session: dict[str, Any], data: dict) -> tuple[str, str]:
    event_id = str(session["next_event_id"])
    session["next_event_id"] += 1
    compact = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return event_id, f"id: {event_id}\nevent: message\ndata: {compact}\n\n"


def _session(request: Request) -> dict[str, Any]:
    session_id = request.headers.get("Mcp-Session-Id")
    if not session_id or session_id not in _sessions:
        raise HTTPException(status_code=404, detail="MCP session not found")
    return _sessions[session_id]


@app.get("/health")
def health() -> dict:
    return {"service": "stats-service", "status": "ok"}


@app.post("/v1/parse")
async def parse(request: Request) -> dict:
    try:
        parameters = _parameters(await request.json())
        text = parameters.get("text")
        if not isinstance(text, str) or not text:
            raise ValueError("text 必须为非空字符串")
        return _success(parse_measurements(text))
    except (json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
        return _invalid_input(exc)


@app.post("/v1/stats")
async def stats(request: Request) -> dict:
    try:
        parameters = _parameters(await request.json())
        values = parameters.get("values")
        if not isinstance(values, list):
            raise ValueError("values 必须为数组")
        return _success(compute_stats(values, parameters.get("target_unit")))
    except (json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
        return _invalid_input(exc)


@app.post("/mcp")
async def mcp_post(request: Request) -> Response:
    try:
        message = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
        )

    method = message.get("method") if isinstance(message, dict) else None
    if method == "initialize":
        response, _ = dispatch(message)
        session_id = uuid.uuid4().hex
        _sessions[session_id] = {"next_event_id": 1, "pending": {}}
        return JSONResponse(response, headers={"Mcp-Session-Id": session_id})

    session = _session(request)
    response, _ = dispatch(message)
    if response is None:
        return Response(status_code=204)

    params = message.get("params", {}) if isinstance(message, dict) else {}
    meta = params.get("_meta", {}) if isinstance(params, dict) else {}
    accepts_sse = "text/event-stream" in request.headers.get("accept", "")
    streams = accepts_sse and meta.get("stream") is True
    if not streams:
        return JSONResponse(response)

    chunks: list[str] = []
    if meta.get("announce_list_changed") or meta.get("drop_before_response"):
        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/tools/list_changed",
        }
        notification_id, chunk = _event(session, notification)
        chunks.append(chunk)
        if meta.get("drop_before_response"):
            session["pending"][notification_id] = response
            return StreamingResponse(iter(chunks), media_type="text/event-stream")

    _, response_chunk = _event(session, response)
    chunks.append(response_chunk)
    return StreamingResponse(iter(chunks), media_type="text/event-stream")


@app.get("/mcp")
async def mcp_get(request: Request) -> Response:
    session = _session(request)
    last_event_id = request.headers.get("Last-Event-ID")
    pending = session["pending"].pop(last_event_id, None)
    if pending is None:
        raise HTTPException(status_code=404, detail="No resumable MCP event")
    _, chunk = _event(session, pending)
    return StreamingResponse(iter([chunk]), media_type="text/event-stream")


@app.delete("/mcp")
async def mcp_delete(request: Request) -> Response:
    session_id = request.headers.get("Mcp-Session-Id")
    if not session_id or session_id not in _sessions:
        raise HTTPException(status_code=404, detail="MCP session not found")
    del _sessions[session_id]
    return Response(status_code=204)
