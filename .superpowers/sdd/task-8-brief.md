# Task 8：stdio 白名单传输

Work from E:\eval-platform. Do not create git commits. Do not revert Task 1–7 files except the listed modify paths.

## Ambiguity resolved by controller

Task 7 made `parse_measurements` `structuredContent` a JSON array (list of measurements), not `{values: [...]}`.
In `test_allowed_alias_runs_full_lifecycle` assert:

`self.assertEqual(result["structuredContent"][0]["unit"], "cm")`

Do not reintroduce session-layer `{values}` wrapping.

`McpSession` already exists in `backend/app/services/mcp/session.py` and talks to any transport with `send`/`close` plus notification collection. Implement `StdioTransport` to that same contract.

On Windows, `IsolatedAsyncioTestCase` may use a selector loop that cannot spawn subprocesses. If so, convert `NotImplementedError` to `MCP_TRANSPORT_ERROR` as specified; also make the lifecycle test use a loop that supports subprocesses if the default loop cannot (e.g. set event loop policy for that test class only), so the allowlisted alias test actually runs rather than skipping.

Place `GET /mcp/stdio-aliases` before path catch-alls in `resources.py`. Permission: `resource:create`.

Do not implement Task 9 runner/probe/catalog.

## Global constraints

- isolated_env; never backend/eval_platform.db
- stdio MCP 只能引用 MCP_STDIO_ALLOWLIST 别名，禁止 Manifest 携带 command/args
- 不保存明文秘密
- 不创建 commit

## Plan text

## Task 8：stdio 白名单传输

**Files:**
- Create: `backend/app/services/mcp/stdio_transport.py`
- Modify: `backend/app/services/mcp/session.py`
- Modify: `backend/app/services/protocol.py`
- Modify: `backend/app/api/resources.py`
- Modify: `backend/tests/test_review_followup_a.py`

**Interfaces:**
- `load_stdio_allowlist(raw: str | None = None) -> dict[str, list[str]]`
- `list_stdio_aliases() -> list[str]`
- `StdioTransport(command_alias: str, *, timeout: int = 30)`
- `GET /api/resources/mcp/stdio-aliases`

- [ ] **Step 1：写 stdio 失败测试**

```python
class McpStdioTransportTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        command = [
            str(Path(sys.executable).resolve()),
            "-m", "tools.stats_service.stdio_server",
        ]
        self.old = os.environ.get("MCP_STDIO_ALLOWLIST")
        os.environ["MCP_STDIO_ALLOWLIST"] = json.dumps({"stats-local": command})

    def tearDown(self):
        # restore env

    async def test_allowed_alias_runs_full_lifecycle(self):
        session = McpSession(StdioTransport("stats-local", timeout=5))
        await session.open()
        tools = await session.list_tools()
        result = await session.call_tool(
            "parse_measurements", {"text": "100 cm"}
        )
        self.assertEqual(len(tools), 2)
        self.assertEqual(result["structuredContent"]["values"][0]["unit"], "cm")
        await session.close()

    async def test_unknown_alias_is_rejected(self):
        with self.assertRaises(McpError) as ctx:
            StdioTransport("powershell -Command whoami")
        self.assertEqual(ctx.exception.code, "MCP_STDIO_NOT_ALLOWED")
```

另加 API 测试：

```python
aliases = client.get("/api/resources/mcp/stdio-aliases", headers=admin_h)
self.assertEqual(aliases.json()["items"], ["stats-local"])
```

- [ ] **Step 2：确认失败**

Run:

```powershell
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.McpStdioTransportTest -v
```

Expected: FAIL，transport 不存在。

- [ ] **Step 3：实现 allowlist 解析**

```python
def load_stdio_allowlist(raw=None):
    data = json.loads(raw if raw is not None else os.getenv("MCP_STDIO_ALLOWLIST", "{}"))
    if not isinstance(data, dict):
        raise McpError("MCP_STDIO_NOT_ALLOWED", "stdio allowlist 必须是对象")
    result = {}
    for alias, command in data.items():
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", alias):
            raise McpError("MCP_STDIO_NOT_ALLOWED", f"非法 alias: {alias}")
        if not isinstance(command, list) or not command:
            raise McpError("MCP_STDIO_NOT_ALLOWED", f"{alias} 命令必须是非空数组")
        executable = Path(str(command[0]))
        if not executable.is_absolute() or not executable.is_file():
            raise McpError("MCP_STDIO_NOT_ALLOWED", f"{alias} 可执行文件必须是绝对路径")
        result[alias] = [str(x) for x in command]
    return result
```

不允许 Manifest 提供 command、args、shell 字符串。

- [ ] **Step 4：实现 StdioTransport**

要求：
- 首次 send 时 `asyncio.create_subprocess_exec(*command, stdin=PIPE, stdout=PIPE, stderr=DEVNULL)`；
- Windows 当前事件循环不支持子进程时捕获 `NotImplementedError`，转换为 `MCP_TRANSPORT_ERROR`；
- 写一行紧凑 JSON + `\n` 后 drain；
- 通知写入后直接返回 None；
- 请求用 `asyncio.wait_for(stdout.readline(), timeout)`；
- 空行/EOF、超过 1 MiB、非法 JSON 均转换稳定错误；
- JSON-RPC id 不匹配时，如为通知则收集并继续读；其他响应抛协议错误；
- `close()` 先关闭 stdin，等待 2 秒，超时 kill，再 await wait。

- [ ] **Step 5：扩展 Manifest 校验与 aliases API**

`executable_errors` 的 MCP 分支：

```python
transport = interfaces.get("transport", "streamable_http")
if transport == "stdio":
    if interfaces.get("command") or interfaces.get("args"):
        errors.append("stdio MCP 只能使用 command_alias")
    if not interfaces.get("command_alias"):
        errors.append("stdio MCP 必须配置 command_alias")
    elif interfaces["command_alias"] not in list_stdio_aliases():
        errors.append("stdio command_alias 不在服务端白名单")
elif transport == "streamable_http":
    if not endpoint.startswith("http"):
        errors.append("Streamable HTTP MCP 必须配置 http(s) endpoint")
else:
    errors.append("MCP transport 仅支持 streamable_http 或 stdio")
```

新增 API：

```python
@router.get("/mcp/stdio-aliases")
async def stdio_aliases(
    _: ActorContext = Depends(require_actor("resource:create")),
):
    return {"items": list_stdio_aliases()}
```

该路由必须位于 `/{rid:path}` 之前。

- [ ] **Step 6：验证**

Run:

```powershell
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.McpStdioTransportTest `
  tests.test_review_followup_d2.ExecutableRegisterTest -v
```

Expected: PASS；未知 alias 与 Manifest command 都被拒绝。

- [ ] **Step 7：记录文件清单**

记录 Task 8 全部文件。

