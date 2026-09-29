from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

from app.services.mcp.errors import McpError

MAX_BODY_BYTES = 1024 * 1024
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ALIAS_RE = re.compile(r"[A-Za-z0-9_.-]+")


def load_stdio_allowlist(raw: str | None = None) -> dict[str, list[str]]:
    data = json.loads(raw if raw is not None else os.getenv("MCP_STDIO_ALLOWLIST", "{}"))
    if not isinstance(data, dict):
        raise McpError("MCP_STDIO_NOT_ALLOWED", "stdio allowlist 必须是对象")
    result: dict[str, list[str]] = {}
    for alias, command in data.items():
        if not _ALIAS_RE.fullmatch(str(alias)):
            raise McpError("MCP_STDIO_NOT_ALLOWED", f"非法 alias: {alias}")
        if not isinstance(command, list) or not command:
            raise McpError("MCP_STDIO_NOT_ALLOWED", f"{alias} 命令必须是非空数组")
        executable = Path(str(command[0]))
        if not executable.is_absolute() or not executable.is_file():
            raise McpError("MCP_STDIO_NOT_ALLOWED", f"{alias} 可执行文件必须是绝对路径")
        result[str(alias)] = [str(x) for x in command]
    return result


def list_stdio_aliases() -> list[str]:
    return list(load_stdio_allowlist().keys())


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(_REPO_ROOT), current) if part
    )
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


class StdioTransport:
    def __init__(self, command_alias: str, *, timeout: int = 30):
        allowlist = load_stdio_allowlist()
        if command_alias not in allowlist:
            raise McpError("MCP_STDIO_NOT_ALLOWED", f"stdio alias 不在白名单: {command_alias}")
        self.command_alias = command_alias
        self.command = allowlist[command_alias]
        self.timeout = timeout
        self.protocol_version: str | None = None
        self.notifications: list[dict] = []
        self._proc: asyncio.subprocess.Process | None = None

    async def _ensure_proc(self) -> asyncio.subprocess.Process:
        if self._proc is not None:
            return self._proc
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=str(_REPO_ROOT),
                env=_child_env(),
            )
        except NotImplementedError as exc:
            raise McpError(
                "MCP_TRANSPORT_ERROR",
                "当前事件循环不支持子进程（Windows Selector loop）",
            ) from exc
        return self._proc

    def _rpc_error(self, payload: dict) -> None:
        err = payload.get("error")
        if not err:
            return
        if isinstance(err, dict):
            message = str(err.get("message") or err)
        else:
            message = str(err)
        raise McpError("MCP_PROTOCOL_ERROR", message)

    async def send(self, message: dict, *, notification: bool = False) -> dict | None:
        proc = await self._ensure_proc()
        if proc.stdin is None or proc.stdout is None:
            raise McpError("MCP_TRANSPORT_ERROR", "stdio pipes unavailable")
        line = json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
        proc.stdin.write(line.encode("utf-8"))
        await proc.stdin.drain()
        if notification:
            return None
        request_id = message.get("id")
        while True:
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=self.timeout)
            except asyncio.TimeoutError as exc:
                raise McpError("MCP_TIMEOUT", "stdio MCP timed out") from exc
            if not raw:
                raise McpError("MCP_TRANSPORT_ERROR", "stdio EOF")
            if len(raw) > MAX_BODY_BYTES:
                raise McpError("MCP_TRANSPORT_ERROR", "stdio message exceeds 1 MiB")
            text = raw.decode("utf-8")
            if not text.strip():
                raise McpError("MCP_TRANSPORT_ERROR", "empty stdio line")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise McpError("MCP_TRANSPORT_ERROR", "invalid JSON response") from exc
            if not isinstance(payload, dict):
                raise McpError("MCP_TRANSPORT_ERROR", "MCP response is not an object")
            if request_id is not None and payload.get("id") == request_id:
                self._rpc_error(payload)
                return payload
            if payload.get("method"):
                self.notifications.append(payload)
                continue
            raise McpError("MCP_PROTOCOL_ERROR", "JSON-RPC id mismatch")

    async def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        if proc.stdin is not None:
            proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
