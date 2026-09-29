# Task 4：提供真实 HTTP 与 MCP 测试服务

## Dependencies

Task 3 已实现：
- `tools.stats_service.core.parse_measurements`
- `tools.stats_service.core.compute_stats`

不得复制统计逻辑。

## Files

- Create: `tools/stats_service/mcp_protocol.py`
- Create: `tools/stats_service/app.py`
- Create: `tools/stats_service/stdio_server.py`
- Create: `tools/stats_service/run.ps1`
- Create: `tools/stats_service/tests/test_http.py`

只改以上文件。

## HTTP interfaces

- `GET /health` → 200，明确 service/status。
- `POST /v1/parse`
- `POST /v1/stats`

后两个接口同时接受：
1. 平台信封参数：`{"body":{"parameters":{...}}}`
2. 裸参数对象。

成功严格返回：

```json
{"status":"success","result":{}}
```

输入错误使用 HTTP 200，返回：

```json
{"status":"error","error":{"code":"INVALID_INPUT","message":"具体原因"}}
```

这用于验证平台能识别 HTTP 200 中的业务失败。

## MCP JSON-RPC

路径：`POST /mcp`、`GET /mcp`、`DELETE /mcp`。

`mcp_protocol.py` 提供：

```python
PROTOCOL_VERSION = "2024-11-05"
TOOLS = {
    "parse_measurements": {
        "name": "parse_measurements",
        "description": "从文本提取数值和单位",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "minLength": 1}},
            "required": ["text"],
        },
    },
    "compute_stats": {
        "name": "compute_stats",
        "description": "转换单位并计算描述统计",
        "inputSchema": {
            "type": "object",
            "properties": {
                "values": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "number"},
                            "unit": {"type": "string"},
                        },
                        "required": ["value", "unit"],
                    },
                    "minItems": 1,
                },
                "target_unit": {"type": "string"},
            },
            "required": ["values"],
        },
    },
}

def dispatch(message: dict) -> tuple[dict | None, dict]:
    """返回 JSON-RPC response（通知为 None）和 metadata。"""
```

协议行为：
- initialize 返回协商 protocolVersion、`capabilities.tools.listChanged=true`、serverInfo；
- initialize HTTP 响应头返回随机 `Mcp-Session-Id`；
- 非 initialize 请求必须携带有效 session id，否则明确 404；
- `notifications/initialized` 无 JSON-RPC response；
- `tools/list` 每页仅 1 个工具：首个响应带 `nextCursor="1"`，cursor=1 返回第二个且不再带 cursor；
- `tools/call` 调用 Task 3 真实函数；
- 参数/业务错误返回 JSON-RPC result，`isError=true`，content 中有错误文本；
- 未知 method 返回 JSON-RPC error code -32601。

Streamable HTTP 测试钩子（真实协议行为，不是常量业务结果）：
- 请求 `Accept` 含 `text/event-stream` 且 `params._meta.stream=true`：SSE 返回；
- `_meta.announce_list_changed=true`：目标 response 前先发 `notifications/tools/list_changed`；
- `_meta.drop_before_response=true`：POST 只发带 `id:` 的通知并缓存目标 response；随后 `GET /mcp` + `Last-Event-ID` 返回缓存 response；
- `DELETE /mcp` 删除 session。

SSE 每个事件使用 `id:`、`event: message`、`data: <compact JSON>`，事件间空行分隔。

## stdio

`python -m tools.stats_service.stdio_server`：
- stdin 按行读取 JSON-RPC；
- 调用同一个 `dispatch`；
- notification 不输出；
- 其他 response 输出单行紧凑 JSON并 flush；
- 非法 JSON 返回 JSON-RPC parse error -32700，不崩溃。

## PowerShell launcher

`run.ps1`：

```powershell
param([int]$Port = 8765)
$root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $root
& "$root\backend\.venv\Scripts\python.exe" -m uvicorn `
  tools.stats_service.app:app --host 127.0.0.1 --port $Port
```

## TDD tests

`test_http.py` 至少覆盖：
1. 信封形式 `/v1/stats` 将 100cm 转为 1m；
2. 裸参数 `/v1/parse`；
3. 非法输入 HTTP 200 + status=error；
4. initialize 返回 session header；
5. initialized notification 无内容/可接受；
6. tools/list 两页共两个工具；
7. compute_stats 空 values 返回 isError=true；
8. SSE JSON-RPC response；
9. list_changed notification 在 response 前；
10. drop + GET Last-Event-ID 恢复；
11. DELETE 后旧 session 失效；
12. stdio 子进程 initialize/list/call 基本生命周期与非法 JSON parse error。

先写测试并观察 RED，再实现。运行：

```powershell
cd E:\eval-platform
backend\.venv\Scripts\python.exe -m unittest `
  tools.stats_service.tests.test_core `
  tools.stats_service.tests.test_http -v
```

GREEN 必须全部 PASS。

## Global constraints

- 这是自建本地 MCP 实测服务，不代表公共服务互操作。
- 不使用 Mock/AsyncMock 替代服务行为。
- 不访问业务数据库、不读取 `.env`、不保存凭证。
- 不新增依赖（复用 backend venv 已有 FastAPI/Pydantic/uvicorn）。
- 当前工作区已有用户改动，不得覆盖、删除或回滚。
- 不创建 commit。

## Report

写入 `.superpowers/sdd/task-4-report.md`，包含 RED/GREEN、各协议分支测试数、文件清单、自审和关注点。
