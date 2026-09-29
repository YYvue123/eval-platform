# Task 4 实施报告：真实 HTTP 与 MCP 测试服务

## Status

完成。实现复用 `tools.stats_service.core.parse_measurements` 与
`tools.stats_service.core.compute_stats`，未复制统计计算逻辑，未实现平台侧 MCP
client，未修改 core 或其他现有文件，未创建 commit。

## TDD 记录

### RED

命令：

```powershell
cd E:\eval-platform
backend\.venv\Scripts\python.exe -m unittest `
  tools.stats_service.tests.test_core `
  tools.stats_service.tests.test_http -v
```

关键输出：

```text
test_http (unittest.loader._FailedTest.test_http) ... ERROR
ModuleNotFoundError: No module named 'tools.stats_service.app'
Ran 11 tests in 0.001s
FAILED (errors=1)
```

失败原因与预期一致：协议测试先创建，而 HTTP/MCP 服务模块尚不存在；原有 10
个 core 测试保持通过。

### GREEN

同一命令最终输出：

```text
Ran 25 tests in 0.234s
OK
```

Task 4 新增 15 个测试方法全部通过；连同 Task 3 的 10 个 core 测试，共
25 个测试通过。

## 协议分支测试数量

- 普通 HTTP：4 个测试方法
  - health 服务标识
  - 平台信封 `/v1/stats`
  - 裸参数 `/v1/parse`
  - HTTP 200 中的 `INVALID_INPUT` 业务失败
- MCP HTTP/JSON-RPC/SSE：10 个测试方法
  - initialize 协商与随机 session header
  - initialized notification 无 JSON-RPC body
  - 缺失/无效 session 的 404
  - tools/list 两页、每页一个工具
  - tools/call 业务错误 `isError=true`
  - 未知 method `-32601`
  - SSE JSON-RPC response
  - list_changed 在目标 response 前
  - drop 后按 `Last-Event-ID` 恢复
  - DELETE 后 session 失效
- stdio：1 个测试方法，覆盖 initialize、notification 静默、list、真实
  tool call、非法 JSON `-32700` 五类输入。

## 创建文件

- `tools/stats_service/mcp_protocol.py`
- `tools/stats_service/app.py`
- `tools/stats_service/stdio_server.py`
- `tools/stats_service/run.ps1`
- `tools/stats_service/tests/test_http.py`

本报告为需求指定的交付记录：
`.superpowers/sdd/task-4-report.md`。

## 实现摘要

- `/v1/parse`、`/v1/stats` 同时接受平台信封和裸参数，输入错误保持 HTTP
  200 并返回严格业务错误信封。
- `dispatch` 集中处理 initialize、分页、真实工具调用、notification 和
  JSON-RPC 错误；HTTP 与 stdio 共用该实现。
- HTTP 层仅负责 session 生命周期、SSE 编码、断线缓存与恢复。
- SSE 事件使用递增 `id:`、`event: message` 和紧凑 JSON `data:`，事件间
  保留空行。
- stdio 按行处理并逐响应 flush；notification 不输出，非法 JSON 不导致进程
  退出。

## Windows / TestClient 行为说明

验证环境为 FastAPI 0.141.1、Starlette 1.6.0。该组合下：

- 显式 `Response(status_code=204)` 的 initialized notification 与 DELETE
  响应均为 204 且 body 为 `b""`，测试保留了状态码和空 body 两项协议断言。
- `StreamingResponse(..., media_type="text/event-stream")` 在 TestClient 中会
  被完整收集，但 `content-type`、事件顺序、事件 ID、空行分隔与恢复结果均可
  按真实响应内容断言，未将流式协议断言删除或降级。
- 测试启动时框架输出
  `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`
  提示；这是当前依赖组合的上游兼容性提示，不影响 25 个测试结果，也未为此
  新增或更改依赖。

## 自审

- 范围：除 5 个实现/测试文件和本报告外未写入任务外文件。
- 复用：HTTP 与 MCP 均直接调用 Task 3 core 函数，没有复制单位换算或统计逻辑。
- 真实性：测试未使用 Mock/AsyncMock，stdio 使用真实子进程，HTTP 使用真实
  FastAPI/Starlette ASGI 应用和响应实现。
- 安全边界：未访问业务数据库、未读取 `.env`、未保存凭证。
- 非目标：未加入平台侧 MCP client，未新增依赖，未创建 commit。
- 静态诊断：4 个 Python 新文件的 IDE linter 诊断为 0。

## 关注点

- 当前服务为需求指定的自建本地 MCP 实测服务，不声明与任意公共 MCP 服务完全
  互操作。
- session 与断线待恢复响应保存在进程内内存中；服务重启会清空，符合本地测试
  服务定位。
- TestClient 的上游弃用提示后续可在统一升级依赖时处理，本 Task 不应单独引入
  新依赖。
