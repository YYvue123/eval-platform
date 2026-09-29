# Task 7 实施报告：Streamable HTTP 传输与 MCP 会话

## Status

完成。新增 `backend/app/services/mcp` 的 Streamable HTTP 传输与会话，未接入
`skill_runtime.run_mcp`，未实现 stdio，未改 Task 4 统计服务，未触碰业务库
`eval_platform.db`，未创建 commit。五条 `McpHttpTransportTest` 对真实
`tools.stats_service` 联调，无 AsyncMock。

## TDD 记录

### RED

命令：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.McpHttpTransportTest -v
```

关键输出：

```text
ImportError: Failed to import test module: test_review_followup_a
ModuleNotFoundError: No module named 'app.services.mcp'
Ran 1 test in 0.000s
FAILED (errors=1)
```

失败原因与预期一致：测试先写入，`app.services.mcp` 尚不存在。

### GREEN

同一命令最终输出：

```text
Ran 5 tests in 7.040s
OK
```

另跑 `ParseSseTest.test_parse_sse_joins_data_and_captures_id` 通过（纯函数
覆盖，不计入上述 5 条）。代码中无 `AsyncMock`。

## What you implemented

- `McpError`：`MCP_AUTH_FAILED` / `MCP_SESSION_EXPIRED` / `MCP_TIMEOUT` /
  `MCP_PROTOCOL_ERROR` / `MCP_TOOL_ERROR` / `MCP_TRANSPORT_ERROR`。
- `HttpTransport`：`assert_egress_allowed` + `httpx_tls_kwargs`；Accept JSON
  与 SSE；会话头 `Mcp-Session-Id` / `MCP-Protocol-Version`；JSON 直接解析；
  SSE 用 `stream()` + `aiter_lines()` 逐行读，1 MiB 上限；匹配请求 id 前收集
  通知并保存非空 event id；流结束且无响应时 GET + `Last-Event-ID` 续读一次；
  `close()` DELETE，204/200/405 视为完成。
- `McpSession`：initialize → 校验 `protocolVersion` → `notifications/initialized`；
  `list_tools` 空 cursor 起最多 20 页、重复 cursor 协议错误；`call_tool` 对
  `isError` 抛 `MCP_TOOL_ERROR`；消费 `notifications/tools/list_changed` 置
  `catalog_changed`。

## 对接 Task 4 的两处客户端适配（未改服务端）

1. 测试把 `_meta` 放在 tool **arguments**，stats_service 读的是 JSON-RPC
   **params._meta**。`call_tool` 把 `_meta` 提升到 params；`announce_list_changed`
   / `drop_before_response` 时补 `stream=True`，否则服务端只回 JSON、不会推
   SSE 通知，也无法 drop+resume。
2. `parse_measurements` 的 `structuredContent` 是测量值 **list**，简报测试访问
   `structuredContent["values"]`。`call_tool` 仅在 list 时包成 `{values: ...}`。

## Self-review

- 范围正确：只新增 mcp 包 + `test_review_followup_a.py` 测试类。
- 未替换 `skill_runtime.run_mcp`，未实现 stdio。
- SSE 不把无限流一次性读入内存。
- 风险：list 包装与 `_meta` 提升是为对齐 Task 4 服务与简报测试的形状差；
  通用 MCP 工具若 `structuredContent` 本就是 list，会被改写。后续 Task 9
  接入网关时应决定是否保留。
- 测试启动 uvicorn 会打 asyncio “took 1.172 seconds” 慢回调警告，不影响结果。

## Files changed

Create:

- `backend/app/services/mcp/__init__.py`
- `backend/app/services/mcp/errors.py`
- `backend/app/services/mcp/http_transport.py`
- `backend/app/services/mcp/session.py`

Modify:

- `backend/tests/test_review_followup_a.py`
  - `McpHttpTransportTest`（简报五条，原文）
  - `ParseSseTest`（`parse_sse` 纯函数）

本报告：`.superpowers/sdd/task-7-report.md`。

## Review follow-up (Important #1 / #2 + cheap Minor)

未 commit。修正两项 Important：`send()` 续读只使用本 POST 流观察到的 event id；`call_tool` 不再把 list 形态的 `structuredContent` 包成 `{values: ...}`，断言对齐 `parse_measurements` 真实返回（测量值 list）。顺带 Minor：`_ingest_event` 仅在 `request_id is not None` 且 `data.id` 匹配时视为 JSON-RPC 响应。

### RED

命令：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_review_followup_a.ParseSseTest.test_ingest_event_requires_request_id_match tests.test_review_followup_a.McpHttpTransportTest.test_send_does_not_resume_with_prior_stream_event_id tests.test_review_followup_a.McpHttpTransportTest.test_json_and_sse_tool_call -v
```

关键输出（改生产代码前）：

```text
FAIL: ingest 在 request_id=None 时把无 id 的 notification 当成响应
FAIL: test_send_does_not_resume... Lists differ: ['evt-prior'] != []
FAIL: test_json_and_sse_tool_call ... AssertionError: 1 != 2
Ran 3 tests in 4.141s
FAILED (failures=3)
```

### GREEN

命令：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_review_followup_a.McpHttpTransportTest -v
```

输出：

```text
test_initialize_notification_and_paginated_catalog ... ok
test_interrupted_stream_resumes_with_last_event_id ... ok
test_json_and_sse_tool_call ... ok
test_list_changed_notification_marks_catalog ... ok
test_tool_is_error_has_stable_code ... ok
Ran 5 tests in ~7s
OK
```

续读隔离 + ingest 单测：

```powershell
.venv\Scripts\python.exe -m unittest tests.test_review_followup_a.HttpTransportResumeTest tests.test_review_followup_a.ParseSseTest -v
```

```text
test_send_does_not_resume_with_prior_stream_event_id ... ok
test_ingest_event_requires_request_id_match ... ok
test_parse_sse_joins_data_and_captures_id ... ok
OK
```

合并 8 条：`Ran 8 tests in 7.948s` / `OK`。无 AsyncMock，未实现 stdio / `run_mcp`。

### Files changed

- `backend/app/services/mcp/http_transport.py` — `_stream_event_id` 每 `send()` 清零；GET `Last-Event-ID` 只用本流 id；公开 `last_event_id` 仍供 drop_before_response 断言；ingest 要求 request id 匹配。
- `backend/app/services/mcp/session.py` — 删除 list → `{values}` 改写。
- `backend/tests/test_review_followup_a.py` — `structuredContent` 按 list 断言；`HttpTransportResumeTest`；ingest 匹配单测。
