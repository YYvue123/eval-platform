# Task 7：Streamable HTTP 传输与 MCP 会话

Work from: E:\eval-platform. Do not create git commits.

## Prior interfaces this task consumes (do not reimplement)

- `from tests.followup_helpers import stats_service` starts tools.stats_service on a free port; MCP path is `{base_url}/mcp`.
- Tools: `parse_measurements`, `compute_stats`; list is paginated one tool per page.
- Test knobs on tool arguments `_meta`: `stream=true` SSE, `announce_list_changed=true`, `drop_before_response=true` plus GET `Last-Event-ID` resume.
- `assert_egress_allowed` lives in `app.services.side_effect_policy`.
- TLS kwargs: `app.services.tls_channel.httpx_tls_kwargs`.

Do not wire this package into `skill_runtime.run_mcp` or the resource gateway yet (Task 9). Do not implement stdio (Task 8). Do not revert unrelated working-tree files. Tests must import `tests.isolated_env` via existing test_review_followup_a.py. No AsyncMock for these five tests.

## Global constraints

- 测试一律先 isolated_env；绝不指向 backend/eval_platform.db。
- 不修改业务库、不调用付费模型；AsyncMock 不能作为真实联调证据。
- 不保存或返回明文秘密。
- 不创建 commit。

## Plan text
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

