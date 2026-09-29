# 子项目 A 实施计划（2/3）：MCP 完整协议

> 先读总计划与 part1。Task 7–9 依赖 Task 4 的自建统计服务。

## Task 7：Streamable HTTP 传输与 MCP 会话

**Files:**
- Create: `backend/app/services/mcp/__init__.py`
- Create: `backend/app/services/mcp/errors.py`
- Create: `backend/app/services/mcp/http_transport.py`
- Create: `backend/app/services/mcp/session.py`
- Modify: `backend/tests/test_review_followup_a.py`

**Interfaces:**

```python
class McpError(RuntimeError):
    code: str
    message: str

class HttpTransport:
    async def send(self, message: dict, *, notification: bool = False) -> dict | None
    async def close(self) -> None

class McpSession:
    async def open(self) -> dict
    async def list_tools(self) -> list[dict]
    async def call_tool(self, name: str, arguments: dict) -> dict
    async def close(self) -> None
```

- [ ] **Step 1：写真实传输失败测试**

在 `test_review_followup_a.py` 添加：

```python
class McpHttpTransportTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = stats_service()
        self.base_url = self.server.__enter__()

    async def asyncTearDown(self):
        self.server.__exit__(None, None, None)

    async def test_initialize_notification_and_paginated_catalog(self):
        session = McpSession(HttpTransport(f"{self.base_url}/mcp", timeout=5))
        info = await session.open()
        tools = await session.list_tools()
        self.assertEqual(info["protocolVersion"], "2024-11-05")
        self.assertEqual(
            [x["name"] for x in tools],
            ["parse_measurements", "compute_stats"],
        )
        self.assertTrue(session.session_id_present)
        await session.close()

    async def test_json_and_sse_tool_call(self):
        session = McpSession(HttpTransport(f"{self.base_url}/mcp", timeout=5))
        await session.open()
        result = await session.call_tool(
            "parse_measurements",
            {"text": "1 m, 20 cm", "_meta": {"stream": True}},
        )
        self.assertEqual(len(result["structuredContent"]["values"]), 2)
        await session.close()

    async def test_tool_is_error_has_stable_code(self):
        session = McpSession(HttpTransport(f"{self.base_url}/mcp", timeout=5))
        await session.open()
        with self.assertRaises(McpError) as ctx:
            await session.call_tool("compute_stats", {"values": []})
        self.assertEqual(ctx.exception.code, "MCP_TOOL_ERROR")
        await session.close()

    async def test_list_changed_notification_marks_catalog(self):
        session = McpSession(HttpTransport(f"{self.base_url}/mcp", timeout=5))
        await session.open()
        await session.call_tool(
            "parse_measurements",
            {"text": "1 m", "_meta": {"announce_list_changed": True}},
        )
        self.assertTrue(session.catalog_changed)
        await session.close()

    async def test_interrupted_stream_resumes_with_last_event_id(self):
        session = McpSession(HttpTransport(f"{self.base_url}/mcp", timeout=5))
        await session.open()
        result = await session.call_tool(
            "parse_measurements",
            {"text": "2 kg", "_meta": {"stream": True, "drop_before_response": True}},
        )
        self.assertEqual(result["structuredContent"]["values"][0]["unit"], "kg")
        self.assertTrue(session.transport.last_event_id)
        await session.close()
```

- [ ] **Step 2：确认失败**

Run:

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.McpHttpTransportTest -v
```

Expected: FAIL，`app.services.mcp` 不存在。

- [ ] **Step 3：实现稳定错误类型**

```python
# errors.py
class McpError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message}
```

映射：
- HTTP 401/403 → `MCP_AUTH_FAILED`
- HTTP 404（已有 session id）→ `MCP_SESSION_EXPIRED`
- timeout → `MCP_TIMEOUT`
- JSON-RPC `error` → `MCP_PROTOCOL_ERROR`
- `result.isError == true` → `MCP_TOOL_ERROR`
- 非法响应/SSE/网络 → `MCP_TRANSPORT_ERROR`

- [ ] **Step 4：实现 SSE 解析**

在 `http_transport.py` 实现纯函数并单测覆盖：

```python
def parse_sse(lines: list[str]) -> list[dict]:
    events = []
    current = {"event": "message", "data": [], "id": ""}
    for line in lines:
        if line == "":
            if current["data"]:
                events.append({
                    "event": current["event"],
                    "id": current["id"],
                    "data": "\n".join(current["data"]),
                })
            current = {"event": "message", "data": [], "id": ""}
        elif line.startswith("data:"):
            current["data"].append(line[5:].lstrip())
        elif line.startswith("event:"):
            current["event"] = line[6:].strip()
        elif line.startswith("id:"):
            current["id"] = line[3:].strip()
    return events
```

实际读取使用 `httpx.AsyncClient.stream()` 与 `response.aiter_lines()`，不得先把无限流全部读入内存。每个事件的 data 必须 JSON 对象。

- [ ] **Step 5：实现 HttpTransport**

构造参数：

```python
HttpTransport(
    endpoint: str,
    *,
    auth_token: str | None = None,
    timeout: int = 30,
    channel: str = "https",
    manifest: dict | None = None,
)
```

行为：
- 调用 `assert_egress_allowed`；
- header 含 `Content-Type: application/json`、`Accept: application/json, text/event-stream`；
- open 之后附加 `Mcp-Session-Id`、`MCP-Protocol-Version`；
- JSON 响应直接处理；
- SSE 持续读取，保存每个非空 `id`；收集通知，直到获得与请求 id 相同的响应；
- 流结束但未得到响应且已有 event id：GET endpoint，带 `Last-Event-ID`，只续读一次；
- `close()` 有 session 时 DELETE endpoint，204/200/405 均视为完成；
- response body 最大 1 MiB，超出抛 `MCP_TRANSPORT_ERROR`。

- [ ] **Step 6：实现 McpSession**

```python
async def open(self):
    response = await self.transport.send({
        "jsonrpc": "2.0", "id": self.next_id(), "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "eval-platform", "version": "0.6.1"},
        },
    })
    # validate result.protocolVersion
    await self.transport.send({
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }, notification=True)
```

`list_tools` 从空 cursor 开始，最多 20 页，重复 cursor 抛协议错误。每次 `send` 后消费 transport 收到的通知；若 method 为 `notifications/tools/list_changed`，置 `catalog_changed=True`。

`call_tool` 对 `result.isError` 抛 `MCP_TOOL_ERROR`，错误消息从 `content[].text` 合并。

- [ ] **Step 7：验证**

Run:

```powershell
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.McpHttpTransportTest -v
```

Expected: 5 tests PASS，未使用 AsyncMock。

- [ ] **Step 8：记录文件清单**

记录 Task 7 全部文件。

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

## Task 9：统一 MCP runner、探测证据与目录快照

**Files:**
- Create: `backend/app/services/mcp/catalog.py`
- Create: `backend/app/services/mcp/runner.py`
- Modify: `backend/app/services/mcp/__init__.py`
- Modify: `backend/app/services/skill_runtime.py`
- Delete: `backend/app/services/mcp_client.py`
- Modify: `backend/app/services/tool_gateway/__init__.py`
- Modify: `backend/app/api/resources.py`
- Modify: `backend/tests/test_tool_gateway.py`
- Modify: `backend/tests/test_review_followup_a.py`

**Interfaces:**
- `async run_mcp(manifest: dict, method: str, params: dict, req_id=1) -> McpRunResult`
- `catalog_hash(tools: list[dict]) -> str`
- `persist_catalog(db, resource_id, tools, *, changed, actor) -> dict`

- [ ] **Step 1：写 runner 与 API 失败测试**

新增：

```python
class McpRunnerApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        self.headers = login_admin(self.client)
        command = [
            str(Path(sys.executable).resolve()),
            "-m", "tools.stats_service.stdio_server",
        ]
        self.old_allowlist = os.environ.get("MCP_STDIO_ALLOWLIST")
        os.environ["MCP_STDIO_ALLOWLIST"] = json.dumps({"stats-local": command})

    def tearDown(self):
        if self.old_allowlist is None:
            os.environ.pop("MCP_STDIO_ALLOWLIST", None)
        else:
            os.environ["MCP_STDIO_ALLOWLIST"] = self.old_allowlist
        self._cm.__exit__(None, None, None)

    def register_mcp(self, rid, interfaces):
        manifest = tool_manifest(rid, "https://unused")
        manifest.update({
            "resource_type": "mcp",
            "interfaces": interfaces,
        })
        response = self.client.post(
            "/api/resources/register",
            json={"manifest": manifest},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)

    def probe(self, rid, method, params=None):
        return self.client.post(
            "/api/resources/mcp/probe",
            json={
                "resource_id": rid,
                "method": method,
                "params": params or {},
            },
            headers=self.headers,
        )

    def test_registered_http_mcp_full_flow_and_probe_log(self):
        rid = f"demo/mcp-http-{uuid.uuid4().hex[:8]}"
        with stats_service() as base_url:
            self.register_mcp(rid, {
                "transport": "streamable_http",
                "endpoint": f"{base_url}/mcp",
                "method": "POST",
            })
            initialized = self.probe(rid, "initialize")
            listed = self.probe(rid, "tools/list")
            called = self.probe(rid, "tools/call", {
                "name": "parse_measurements",
                "arguments": {"text": "1 m, 20 cm"},
            })
        self.assertTrue(initialized.json()["ok"])
        self.assertEqual(
            initialized.json()["session"]["protocol_version"],
            "2024-11-05",
        )
        self.assertTrue(initialized.json()["session"]["session_id_present"])
        self.assertEqual(len(listed.json()["result"]["tools"]), 2)
        self.assertTrue(called.json()["ok"])
        history = self.client.get(
            f"/api/resources/calls/{rid}",
            headers=self.headers,
        ).json()
        self.assertGreaterEqual(history["total"], 3)
        self.assertTrue(all(x["source"] == "mcp_probe" for x in history["items"]))

    def test_registered_stdio_mcp_full_flow(self):
        rid = f"demo/mcp-stdio-{uuid.uuid4().hex[:8]}"
        self.register_mcp(rid, {
            "transport": "stdio",
            "command_alias": "stats-local",
        })
        listed = self.probe(rid, "tools/list")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertTrue(listed.json()["ok"])
        self.assertEqual(len(listed.json()["result"]["tools"]), 2)

    def test_tool_is_error_is_not_green(self):
        rid = f"demo/mcp-error-{uuid.uuid4().hex[:8]}"
        with stats_service() as base_url:
            self.register_mcp(rid, {
                "transport": "streamable_http",
                "endpoint": f"{base_url}/mcp",
                "method": "POST",
            })
            response = self.probe(rid, "tools/call", {
                "name": "compute_stats",
                "arguments": {"values": []},
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(response.json()["error"]["code"], "MCP_TOOL_ERROR")
        history = self.client.get(
            f"/api/resources/calls/{rid}",
            headers=self.headers,
        ).json()
        self.assertEqual(history["items"][0]["status"], "failed")

    def test_catalog_change_event_marks_detail_stale(self):
        rid = f"demo/mcp-stale-{uuid.uuid4().hex[:8]}"
        with stats_service() as base_url:
            self.register_mcp(rid, {
                "transport": "streamable_http",
                "endpoint": f"{base_url}/mcp",
                "method": "POST",
            })
            listed = self.probe(rid, "tools/list")
            self.assertTrue(listed.json()["ok"])
            changed = self.probe(rid, "tools/call", {
                "name": "parse_measurements",
                "arguments": {
                    "text": "1 m",
                    "_meta": {"announce_list_changed": True},
                },
            })
            self.assertTrue(changed.json()["ok"])
        detail = self.client.get(
            f"/api/resources/{rid}",
            headers=self.headers,
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertTrue(detail.json()["mcp_catalog"]["stale"])
```

- [ ] **Step 2：实现 transport 工厂与 runner**

```python
def transport_from_manifest(manifest):
    interfaces = manifest.get("interfaces") or {}
    if interfaces.get("transport", "streamable_http") == "stdio":
        return StdioTransport(
            str(interfaces.get("command_alias") or ""),
            timeout=timeout,
        )
    return HttpTransport(
        endpoint,
        auth_token=resolve_credential(interfaces),
        timeout=timeout,
        channel=str(interfaces.get("channel") or "https"),
        manifest=manifest,
    )
```

`run_mcp` 每次创建会话，`try/finally close()`：
- `initialize`：仅 `open()`；
- `tools/list`：open 后聚合分页；
- `tools/call`：open 后调用；
- 其他方法：open 后通过 session 的 `request(method, params)`；
- 返回 dataclass：

```python
@dataclass
class McpRunResult:
    result: dict
    protocol_version: str
    server_info: dict
    session_id_present: bool
    notifications: list[dict]
    catalog_changed: bool
```

- [ ] **Step 3：替换旧运行路径**

`skill_runtime.py` 删除远程 MCP 实现和 `mcp_client` imports，只保留：
- Skill 工作流函数；
- 内置 `builtin/mcp_gateway` 的本地行为（如继续保留）；
- 非内置 MCP 调用委托 `services.mcp.run_mcp`。

`tool_gateway` 的 MCP 分支：

```python
run = await run_mcp(manifest, method, rpc_params, req_id=req_id)
result = run.result
```

任何 `McpError` 必须由通用异常分支记为 failed；响应 error code 使用 `exc.code`，不能统一覆盖成 `TOOL_EXEC_FAILED`：

```python
code = getattr(exc, "code", "TOOL_EXEC_FAILED")
```

- [ ] **Step 4：实现目录 hash 与事件**

```python
def catalog_hash(tools):
    canonical = json.dumps(
        sorted(tools, key=lambda x: x.get("name", "")),
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
```

`persist_catalog` 查询该资源最后一个 `mcp.catalog` 事件：
- 成功 list 写 `mcp.catalog`，payload 只有 hash、count、tool_names、tenant_id；
- hash 改变或 session 收到 list_changed，另写 `mcp.catalog_changed`；
- 不保存工具 schema 中可能出现的 secret default。

`resource_out` 为 MCP 资源追加：

```python
"mcp_catalog": {
    "hash": latest_hash,
    "count": count,
    "observed_at": iso(event.created_at),
    "stale": latest_changed_id > latest_catalog_id,
}
```

由于 `resource_out` 当前是同步函数，目录摘要应由详情接口异步查询后附加，不要在 serializer 内查询数据库。

- [ ] **Step 5：probe 归一与落库**

`McpProbeBody` 增加：

```python
transport: str = "streamable_http"
command_alias: str = ""
```

临时探测：
- HTTP 可传 endpoint/token（token 只在内存使用）；
- stdio 只传 command_alias；
- 两类来源继续互斥。

返回：

```python
{
  "ok": error is None,
  "mode": mode,
  "target": target,
  "transport": transport,
  "probed_at": "2026-09-29T01:00:00Z",
  "session": {
    "protocol_version": run.protocol_version,
    "server_info": run.server_info,
    "session_id_present": run.session_id_present,
  },
  "error": error.as_dict() if error else None,
  "result": run.result if run else None,
  "notifications": run.notifications if run else [],
}
```

已注册资源 probe 调用 `invoke_tool` 时显式传 `caller_id="mcp_probe"`，从而自动落证据。临时探测手动写 `ResourceCallLog(resource_id=f"adhoc-mcp:{host_or_alias}", source="mcp_probe")`，digest 不能包含 token。

- [ ] **Step 6：移除旧 AsyncMock 测试**

删除 `test_tool_gateway.RemoteMcpClientTest` 和 `backend/app/services/mcp_client.py`。保留/更新 builtin MCP 用例；真实协议覆盖由 Task 7–9 子进程测试提供。

- [ ] **Step 7：验证 MCP 后端**

Run:

```powershell
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.McpHttpTransportTest `
  tests.test_review_followup_a.McpStdioTransportTest `
  tests.test_review_followup_a.McpRunnerApiTest `
  tests.test_tool_gateway.McpSkillApiTest -v
```

Expected: 全部 PASS；HTTP、SSE、恢复、stdio 都使用真实子进程。

- [ ] **Step 8：记录文件清单**

记录 Task 9 全部文件。
