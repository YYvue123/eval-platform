"""外部 HTTP 工具适配：用 Manifest interfaces 转发信封。"""
from __future__ import annotations

from app.services.tls_channel import httpx_tls_kwargs
import httpx


async def invoke_http_tool(manifest: dict, envelope: dict) -> dict:
    interfaces = manifest.get("interfaces") or {}
    url = interfaces.get("endpoint") or interfaces.get("url") or ""
    if not str(url).startswith("http"):
        raise RuntimeError("外部工具未配置 HTTP endpoint")
    method = (interfaces.get("method") or "POST").upper()
    headers = {"Content-Type": "application/json"}
    auth = interfaces.get("auth") or {}
    if auth.get("type") == "bearer" and auth.get("token"):
        headers["Authorization"] = f"Bearer {auth['token']}"
    timeout = int((manifest.get("capabilities") or {}).get("timeout") or 30)
    async with httpx.AsyncClient(timeout=timeout, **httpx_tls_kwargs(str(interfaces.get("channel") or "https"))) as client:
        resp = await client.request(method, url, json=envelope, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    if isinstance(data, dict) and "body" in data:
        return data.get("body") or {}
    return data if isinstance(data, dict) else {"result": data}


async def health_http_tool(manifest: dict) -> dict:
    interfaces = manifest.get("interfaces") or {}
    url = interfaces.get("health") or interfaces.get("endpoint") or ""
    if not str(url).startswith("http"):
        return {"ok": False, "detail": "无 HTTP 健康检查地址"}
    try:
        async with httpx.AsyncClient(timeout=10, **httpx_tls_kwargs(str(interfaces.get("channel") or "https"))) as client:
            resp = await client.get(url)
        return {"ok": resp.status_code < 500, "detail": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}
