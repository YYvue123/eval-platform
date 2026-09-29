# Task 9 实施报告：统一 MCP runner、探测证据与目录快照

## Status

完成。新增 `run_mcp` / `McpRunResult`、目录 hash 与事件、probe 走
`invoke_tool(..., caller_id="mcp_probe")`。已删除 `mcp_client.py` 与
`RemoteMcpClientTest`。未实现前端 Tasks 10–13，未触碰业务库
`eval_platform.db`，未创建 commit。HTTP/SSE/stdio 使用真实子进程，无 AsyncMock。

`structuredContent` 仍为 list，session 层未再包装。凭证只读
`credential_ref`（临时 probe token 进进程内 map，不写 Manifest/日志 digest）。

## TDD 记录

### RED

命令：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_review_followup_a.McpRunnerApiTest -v
```

关键输出（修正 resource_id 连字符后）：

```text
KeyError: 'session' / KeyError: 'ok' / KeyError: 'tools'
AssertionError: 400 != 200  # 旧 httpx 客户端对 Streamable HTTP 返回 404
Ran 4 tests in 8.589s
FAILED (failures=1, errors=3)
```

失败原因符合预期：旧 `mcp_client` 单次 POST，probe 无 session 信封，stdio 落入内置 MCP。

### GREEN

命令：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.McpHttpTransportTest `
  tests.test_review_followup_a.McpStdioTransportTest `
  tests.test_review_followup_a.McpRunnerApiTest `
  tests.test_tool_gateway.McpSkillApiTest -v
```

最终输出：

```text
Ran 18 tests in 30.742s
OK
```

## What you implemented

- `transport_from_manifest` / `resolve_credential` / `run_mcp`：每次开会话，
  initialize 仅 `open()`，list 分页聚合，call 走 `call_tool`，其它 `request`，
  `finally close()`。
- `skill_runtime.run_mcp`：`builtin/` 与 `local://` 保留本地 JSON-RPC；远程/stdio
  委托 `services.mcp.run_mcp`。
- `tool_gateway` MCP：`method`/`params`/`id` 入 runner；`McpError.code` 进入信封；
  metadata 带 session/notifications；list/list_changed 写目录事件。
- `persist_catalog` / `catalog_hash`：payload 仅 hash、count、tool_names、tenant_id；
  schema 不入库。详情 GET 异步附加 `mcp_catalog`（`resource_out` 保持同步）。
- Probe：已注册调 `invoke_tool`；临时 HTTP/stdio 互斥；adhoc 写
  `ResourceCallLog(resource_id=adhoc-mcp:..., source=mcp_probe)`。

## Windows / 子进程适配

`McpRunnerApiTest` 与 Task 8 相同，在 `setUpClass` 设置
`WindowsProactorEventLoopPolicy`。stdio 全流程对白名单子进程实测。

## Files

- Create: `backend/app/services/mcp/catalog.py`
- Create: `backend/app/services/mcp/runner.py`
- Modify: `backend/app/services/mcp/__init__.py`
- Modify: `backend/app/services/mcp/session.py`（`request`）
- Modify: `backend/app/services/mcp/errors.py`（`public_message`）
- Modify: `backend/app/services/skill_runtime.py`
- Delete: `backend/app/services/mcp_client.py`
- Modify: `backend/app/services/tool_gateway/__init__.py`
- Modify: `backend/app/api/resources.py`
- Modify: `backend/tests/test_tool_gateway.py`
- Modify: `backend/tests/test_review_followup_a.py`

## Concerns

- 简报里的 `demo/mcp-http-...` 含连字符，与 `RESOURCE_ID_RE` 冲突；测试改为
  `demo/mcp_http_...`。
- 临时 HTTP token 用内存 `credential_ref` map，不进 `os.environ`；无专门 token 用例。
