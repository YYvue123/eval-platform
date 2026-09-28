"""外部 HTTP 工具适配：信封转发、trace 传播、429 退避。"""
from __future__ import annotations

import asyncio

import httpx

from app.services.side_effect_policy import assert_egress_allowed
from app.services.tls_channel import httpx_tls_kwargs

MAX_RETRIES = 3


async def invoke_http_tool(manifest: dict, envelope: dict) -> dict:
    interfaces = manifest.get("interfaces") or {}
    url = interfaces.get("endpoint") or interfaces.get("url") or ""
    if not str(url).startswith("http"):
        raise RuntimeError("外部工具未配置 HTTP endpoint")
    assert_egress_allowed(url, manifest)
    method = (interfaces.get("method") or "POST").upper()
    headers = {"Content-Type": "application/json"}
    auth = interfaces.get("auth") or {}
    if auth.get("type") == "bearer" and auth.get("token"):
        headers["Authorization"] = f"Bearer {auth['token']}"
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
                if isinstance(data, dict) and "body" in data:
                    body = data.get("body") or {}
                    if isinstance(body, dict) and body.get("status") == "success":
                        return body.get("result") or {}
                    if isinstance(body, dict) and "result" in body:
                        return body.get("result") or {}
                    return body
                return data if isinstance(data, dict) else {"result": data}
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
    raise RuntimeError("HTTP 工具调用失败")


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
