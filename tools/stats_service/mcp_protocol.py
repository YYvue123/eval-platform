from __future__ import annotations

import json
from typing import Any

from tools.stats_service.core import compute_stats, parse_measurements

PROTOCOL_VERSION = "2024-11-05"

TOOLS = {
    "parse_measurements": {
        "name": "parse_measurements",
        "description": "从文本提取数值和单位",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "minLength": 1}},
            "required": ["text"],
        },
    },
    "compute_stats": {
        "name": "compute_stats",
        "description": "转换单位并计算描述统计",
        "inputSchema": {
            "type": "object",
            "properties": {
                "values": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "number"},
                            "unit": {"type": "string"},
                        },
                        "required": ["value", "unit"],
                    },
                    "minItems": 1,
                },
                "target_unit": {"type": "string"},
            },
            "required": ["values"],
        },
    },
}


def _result(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _tool_result(value: Any) -> dict:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": value,
        "isError": False,
    }


def _tool_error(exc: Exception) -> dict:
    return {
        "content": [{"type": "text", "text": str(exc)}],
        "isError": True,
    }


def _call_tool(params: Any) -> dict:
    if not isinstance(params, dict):
        return _tool_error(ValueError("params 必须为对象"))
    name = params.get("name")
    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        return _tool_error(ValueError("arguments 必须为对象"))

    try:
        if name == "parse_measurements":
            text = arguments.get("text")
            if not isinstance(text, str) or not text:
                raise ValueError("text 必须为非空字符串")
            return _tool_result(parse_measurements(text))
        if name == "compute_stats":
            values = arguments.get("values")
            if not isinstance(values, list):
                raise ValueError("values 必须为数组")
            target_unit = arguments.get("target_unit")
            return _tool_result(compute_stats(values, target_unit))
        raise ValueError(f"未知工具: {name}")
    except (TypeError, ValueError, OverflowError) as exc:
        return _tool_error(exc)


def dispatch(message: dict) -> tuple[dict | None, dict]:
    """返回 JSON-RPC response（通知为 None）和 metadata。"""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request"), {}

    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params", {})
    metadata = {"method": method}

    if method == "initialize":
        response = _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "stats-service", "version": "1.0.0"},
            },
        )
    elif method == "notifications/initialized":
        response = None
    elif method == "tools/list":
        cursor = params.get("cursor") if isinstance(params, dict) else None
        tools = list(TOOLS.values())
        if cursor in (None, ""):
            response = _result(
                request_id, {"tools": [tools[0]], "nextCursor": "1"}
            )
        elif str(cursor) == "1":
            response = _result(request_id, {"tools": [tools[1]]})
        else:
            response = _error(request_id, -32602, "Invalid cursor")
    elif method == "tools/call":
        response = _result(request_id, _call_tool(params))
    else:
        response = _error(request_id, -32601, "Method not found")

    if "id" not in message:
        response = None
    return response, metadata
