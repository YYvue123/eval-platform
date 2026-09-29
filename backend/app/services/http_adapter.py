"""外部 HTTP 工具适配：信封转发、trace 传播、429 退避。"""
from __future__ import annotations

import asyncio
import os

import httpx

from app.services.redaction import redact_error_text, safe_error_message
from app.services.side_effect_policy import assert_egress_allowed
from app.services.tls_channel import httpx_tls_kwargs

MAX_RETRIES = 3

_FAIL_STATUS = {"error", "failed", "blocked", "denied"}


class HttpToolError(RuntimeError):
    def __init__(self, public_message: str, code: str = "TOOL_EXEC_FAILED"):
        super().__init__("HTTP tool execution failed")
        self.public_message = redact_error_text(public_message)
        self.code = code


def _safe_error_value(value) -> str:
    if isinstance(value, (dict, list)):
        return safe_error_message(value)
    return "上游工具返回错误"


def _require_explicit_success(data) -> dict:
    """只有明确 status=success 且没有协议错误才算执行成功。"""
    if not isinstance(data, dict):
        raise HttpToolError("HTTP 工具响应不是对象，缺少明确成功状态")
    if data.get("stubbed") or data.get("mocked") or data.get("isError") is True:
        raise HttpToolError("HTTP 工具返回 stub/isError，不能记为成功")
    protocol_error = data.get("error")
    if isinstance(protocol_error, (dict, list)) and protocol_error:
        message = (
            protocol_error.get("message") or protocol_error
            if isinstance(protocol_error, dict)
            else protocol_error
        )
        raise HttpToolError(f"HTTP 工具协议错误: {_safe_error_value(message)}")
    body = data.get("body") if "body" in data else data
    if not isinstance(body, dict):
        raise HttpToolError("HTTP 工具响应缺少明确成功状态")
    if body.get("stubbed") or body.get("mocked") or body.get("isError") is True:
        raise HttpToolError("HTTP 工具返回 stub/isError，不能记为成功")
    status = str(body.get("status") or "").lower()
    if status in _FAIL_STATUS:
        err = body.get("error") or body.get("message") or status
        raise HttpToolError(f"HTTP 工具业务失败: {_safe_error_value(err)}")
    if status != "success":
        raise HttpToolError("HTTP 工具响应缺少明确成功状态")
    result = body.get("result") if "result" in body else {k: v for k, v in body.items() if k != "status"}
    return result if isinstance(result, dict) else {"result": result}


async def invoke_http_tool(manifest: dict, envelope: dict) -> dict:
    interfaces = manifest.get("interfaces") or {}
    url = interfaces.get("endpoint") or interfaces.get("url") or ""
    if not str(url).startswith("http"):
        raise HttpToolError("外部工具未配置 HTTP endpoint")
    assert_egress_allowed(url, manifest)
    method = (interfaces.get("method") or "POST").upper()
    headers = {"Content-Type": "application/json"}
    auth = interfaces.get("auth") or {}
    token = ""
    if isinstance(auth, dict) and auth.get("credential_ref"):
        token = os.environ.get(str(auth["credential_ref"]), "")
    elif isinstance(auth, dict) and auth.get("type") == "bearer" and auth.get("token"):
        token = str(auth["token"])
    if token:
        headers["Authorization"] = f"Bearer {token}"
    tr = envelope.get("trace") or {}
    if tr.get("traceparent"):
        headers["traceparent"] = tr["traceparent"]
    if tr.get("trace_id"):
        headers["X-Trace-Id"] = tr["trace_id"]
    if tr.get("parent_span_id") or tr.get("parent_trace_id"):
        headers["X-Parent-Trace-Id"] = tr.get("parent_span_id") or tr.get("parent_trace_id")
    timeout = int((manifest.get("capabilities") or {}).get("timeout") or 30)
    delay = 0.5
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=timeout, **httpx_tls_kwargs(str(interfaces.get("channel") or "https"))) as client:
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.request(method, url, json=envelope, headers=headers)
                if resp.status_code == 429 and attempt < MAX_RETRIES - 1:
                    ra = resp.headers.get("Retry-After")
                    wait = float(ra) if ra and str(ra).replace(".", "", 1).isdigit() else delay
                    await asyncio.sleep(wait)
                    delay = min(delay * 2, 8)
                    continue
                resp.raise_for_status()
                data = resp.json()
                return _require_explicit_success(data)
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response is not None and exc.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 8)
                    continue
                raise
            except Exception as exc:
                last_exc = exc
                raise
    if last_exc:
        raise last_exc
    raise HttpToolError("HTTP 工具调用失败")


async def health_http_tool(manifest: dict) -> dict:
    interfaces = manifest.get("interfaces") or {}
    url = interfaces.get("health") or interfaces.get("endpoint") or ""
    if not str(url).startswith("http"):
        return {"ok": False, "detail": "无 HTTP 健康检查地址"}
    try:
        async with httpx.AsyncClient(timeout=10, **httpx_tls_kwargs(str(interfaces.get("channel") or "https"))) as client:
            resp = await client.get(url)
        ok = 200 <= resp.status_code < 300
        return {"ok": ok, "status": "online" if ok else "abnormal", "detail": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}
