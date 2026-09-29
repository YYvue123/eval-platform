from __future__ import annotations

from app.services.mcp.errors import McpError


class McpSession:
    def __init__(self, transport):
        self.transport = transport
        self.catalog_changed = False
        self._next_id = 0
        self.notifications: list[dict] = []

    def next_id(self) -> int:
        self._next_id += 1
        return self._next_id

    @property
    def session_id_present(self) -> bool:
        return bool(getattr(self.transport, "session_id", None))

    def _consume_notifications(self) -> None:
        pending = list(getattr(self.transport, "notifications", []) or [])
        if hasattr(self.transport, "notifications"):
            self.transport.notifications.clear()
        for note in pending:
            self.notifications.append(note)
            if note.get("method") == "notifications/tools/list_changed":
                self.catalog_changed = True

    def _tool_params(self, name: str, arguments: dict) -> dict:
        arguments = dict(arguments or {})
        meta = arguments.get("_meta")
        params: dict = {"name": name, "arguments": arguments}
        if isinstance(meta, dict):
            lifted = dict(meta)
            if lifted.get("announce_list_changed") or lifted.get("drop_before_response"):
                lifted["stream"] = True
            params["_meta"] = lifted
        return params

    async def open(self) -> dict:
        response = await self.transport.send({
            "jsonrpc": "2.0",
            "id": self.next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "eval-platform", "version": "0.6.1"},
            },
        })
        result = (response or {}).get("result")
        if not isinstance(result, dict) or not result.get("protocolVersion"):
            raise McpError("MCP_PROTOCOL_ERROR", "initialize missing protocolVersion")
        self.transport.protocol_version = str(result["protocolVersion"])
        await self.transport.send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }, notification=True)
        self._consume_notifications()
        return result

    async def list_tools(self) -> list[dict]:
        tools: list[dict] = []
        cursor = ""
        seen: set[str] = set()
        for _ in range(20):
            params: dict = {}
            if cursor:
                params["cursor"] = cursor
            response = await self.transport.send({
                "jsonrpc": "2.0",
                "id": self.next_id(),
                "method": "tools/list",
                "params": params,
            })
            self._consume_notifications()
            result = (response or {}).get("result")
            if not isinstance(result, dict):
                raise McpError("MCP_PROTOCOL_ERROR", "tools/list missing result")
            page = result.get("tools") or []
            if not isinstance(page, list):
                raise McpError("MCP_PROTOCOL_ERROR", "tools/list tools is not a list")
            tools.extend(page)
            next_cursor = result.get("nextCursor")
            if not next_cursor:
                return tools
            token = str(next_cursor)
            if token in seen:
                raise McpError("MCP_PROTOCOL_ERROR", "repeated tools/list cursor")
            seen.add(token)
            cursor = token
        raise McpError("MCP_PROTOCOL_ERROR", "tools/list exceeded 20 pages")

    async def call_tool(self, name: str, arguments: dict) -> dict:
        response = await self.transport.send({
            "jsonrpc": "2.0",
            "id": self.next_id(),
            "method": "tools/call",
            "params": self._tool_params(name, arguments),
        })
        self._consume_notifications()
        result = (response or {}).get("result")
        if not isinstance(result, dict):
            raise McpError("MCP_PROTOCOL_ERROR", "tools/call missing result")
        if result.get("isError") is True:
            texts = []
            for item in result.get("content") or []:
                if isinstance(item, dict) and item.get("text"):
                    texts.append(str(item["text"]))
            raise McpError("MCP_TOOL_ERROR", "\n".join(texts) or "MCP tool error")
        return result

    async def request(self, method: str, params: dict) -> dict:
        response = await self.transport.send({
            "jsonrpc": "2.0",
            "id": self.next_id(),
            "method": method,
            "params": params or {},
        })
        self._consume_notifications()
        result = (response or {}).get("result")
        if not isinstance(result, dict):
            raise McpError("MCP_PROTOCOL_ERROR", f"{method} missing result")
        return result

    async def close(self) -> None:
        await self.transport.close()
