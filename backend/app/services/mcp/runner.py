from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.services.mcp.errors import McpError
from app.services.mcp.http_transport import HttpTransport
from app.services.mcp.session import McpSession
from app.services.mcp.stdio_transport import StdioTransport


_TEMP_CREDENTIALS: dict[str, str] = {}


def resolve_credential(interfaces: dict) -> str | None:
    auth = interfaces.get("auth") if isinstance(interfaces.get("auth"), dict) else {}
    ref = auth.get("credential_ref")
    if not ref:
        return None
    key = str(ref)
    if key in _TEMP_CREDENTIALS:
        return _TEMP_CREDENTIALS[key] or None
    return os.environ.get(key) or None


def bind_temp_credential(token: str) -> str:
    key = f"MCP_PROBE_TOKEN_{id(token)}-{os.urandom(4).hex()}"
    _TEMP_CREDENTIALS[key] = token
    return key


def unbind_temp_credential(key: str) -> None:
    _TEMP_CREDENTIALS.pop(key, None)


def transport_from_manifest(manifest: dict):
    interfaces = manifest.get("interfaces") or {}
    timeout = int((manifest.get("capabilities") or {}).get("timeout") or 30)
    if interfaces.get("transport", "streamable_http") == "stdio":
        return StdioTransport(
            str(interfaces.get("command_alias") or ""),
            timeout=timeout,
        )
    endpoint = str(interfaces.get("endpoint") or interfaces.get("url") or "")
    return HttpTransport(
        endpoint,
        auth_token=resolve_credential(interfaces),
        timeout=timeout,
        channel=str(interfaces.get("channel") or "https"),
        manifest=manifest,
    )


@dataclass
class McpRunResult:
    result: dict
    protocol_version: str = ""
    server_info: dict = field(default_factory=dict)
    session_id_present: bool = False
    notifications: list[dict] = field(default_factory=list)
    catalog_changed: bool = False


async def run_mcp(manifest: dict, method: str, params: dict, req_id=1) -> McpRunResult:
    del req_id
    session = McpSession(transport_from_manifest(manifest or {}))
    try:
        info = await session.open()
        method = str(method or "")
        params = params if isinstance(params, dict) else {}
        if method in {"initialize", "mcp/initialize"}:
            result = info
        elif method in {"tools/list", "list_tools"}:
            result = {"tools": await session.list_tools()}
        elif method in {"tools/call", "call_tool"}:
            name = str(params.get("name") or params.get("resource_id") or "")
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            if not name:
                raise McpError("MCP_PROTOCOL_ERROR", "缺少 tool name")
            result = await session.call_tool(name, arguments)
        else:
            result = await session.request(method, params)
        if not isinstance(result, dict):
            result = {"result": result}
        return McpRunResult(
            result=result,
            protocol_version=str(
                getattr(session.transport, "protocol_version", None)
                or info.get("protocolVersion")
                or ""
            ),
            server_info=info.get("serverInfo") if isinstance(info.get("serverInfo"), dict) else {},
            session_id_present=session.session_id_present,
            notifications=list(session.notifications),
            catalog_changed=bool(session.catalog_changed),
        )
    finally:
        await session.close()
