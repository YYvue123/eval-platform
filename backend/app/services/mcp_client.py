"""远程 MCP JSON-RPC 客户端（HTTP）。"""
from __future__ import annotations

import httpx

from app.services.side_effect_policy import assert_egress_allowed
from app.services.tls_channel import httpx_tls_kwargs


async def mcp_request(
    endpoint: str,
    method: str,
    params: dict | None = None,
    *,
    req_id: int | str = 1,
    auth_token: str | None = None,
    timeout: int = 30,
    channel: str = "https",
    manifest: dict | None = None,
) -> dict:
    if not str(endpoint).startswith("http"):
        raise ValueError("远程 MCP 需要 HTTP(S) endpoint")
    assert_egress_allowed(endpoint, manifest)
    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    async with httpx.AsyncClient(timeout=timeout, **httpx_tls_kwargs(channel)) as client:
        resp = await client.post(endpoint, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError("MCP 响应非 JSON 对象")
    if data.get("error"):
        err = data["error"]
        raise RuntimeError(err.get("message") if isinstance(err, dict) else str(err))
    return data


async def mcp_initialize(endpoint: str, **kwargs) -> dict:
    return await mcp_request(
        endpoint,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "eval-platform", "version": "0.6.1"},
        },
        **kwargs,
    )


async def mcp_tools_list(endpoint: str, **kwargs) -> dict:
    return await mcp_request(endpoint, "tools/list", {}, **kwargs)


async def mcp_tools_call(endpoint: str, name: str, arguments: dict | None = None, **kwargs) -> dict:
    return await mcp_request(
        endpoint,
        "tools/call",
        {"name": name, "arguments": arguments or {}},
        **kwargs,
    )
