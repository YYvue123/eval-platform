"""L3 本地 HTTP MCP echo（JSON-RPC）：initialize / tools/list / tools/call。"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


TOOLS = [
    {
        "name": "echo",
        "description": "Echo text for L3 MCP protocol probe",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    }
]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # quieter
        pass

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/mcp":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            return
        rid = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "l3-mcp-echo", "version": "0.1.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if name != "echo":
                self._json(
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": rid,
                        "error": {"code": -32601, "message": f"unknown tool {name}"},
                    },
                )
                return
            text = str(args.get("text", ""))
            result = {"content": [{"type": "text", "text": f"echo:{text}"}], "isError": False}
        elif method == "notifications/initialized":
            self._json(200, {"jsonrpc": "2.0", "id": rid, "result": {}})
            return
        else:
            self._json(
                200,
                {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method {method}"}},
            )
            return
        self._json(200, {"jsonrpc": "2.0", "id": rid, "result": result})

    def _json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    host, port = "127.0.0.1", 8765
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"l3-mcp-echo http://{host}:{port}/mcp", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
