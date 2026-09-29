# Task 8 实施报告：stdio 白名单传输

## Status

完成。新增 `StdioTransport` 与 `MCP_STDIO_ALLOWLIST` 解析，扩展 MCP Manifest
校验与 `GET /api/resources/mcp/stdio-aliases`。未实现 Task 9 runner/probe/catalog，
未接入 `skill_runtime.run_mcp`，未改 Task 4 统计服务，未触碰业务库
`eval_platform.db`，未创建 commit。生命周期测试对真实
`python -m tools.stats_service.stdio_server` 子进程联调，无 AsyncMock。

`structuredContent` 保持 Task 4 的 list 形状，测试断言
`result["structuredContent"][0]["unit"] == "cm"`，未再包 `{values: ...}`。

`session.py` 已满足 `send`/`close` 与通知收集契约，本任务未改该文件。

## TDD 记录

### RED

命令：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.McpStdioTransportTest -v
```

关键输出：

```text
ModuleNotFoundError: No module named 'app.services.mcp.stdio_transport'
AssertionError: 404 != 200  # GET /mcp/stdio-aliases 落入 /{rid:path}
AssertionError: 'command_alias' not found  # 仍报「MCP 必须配置 http(s) endpoint」
Ran 4 tests in 4.655s
FAILED (failures=2, errors=2)
```

失败原因与预期一致：transport 与 aliases 路由尚不存在，stdio Manifest 仍走 HTTP 校验。

### GREEN

命令：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.McpStdioTransportTest `
  tests.test_review_followup_d2.ExecutableRegisterTest -v
```

最终输出：

```text
Ran 7 tests in 7.257s
OK
```

`McpStdioTransportTest` 4 条 + `ExecutableRegisterTest` 3 条。未知 alias 与
Manifest `command`/`args` 均被拒绝。代码中无 `AsyncMock`。

## What you implemented

- `load_stdio_allowlist` / `list_stdio_aliases`：别名正则、绝对路径可执行文件、
  非空 argv 数组；未知 alias → `MCP_STDIO_NOT_ALLOWED`。
- `StdioTransport`：首次 `send` 时 `create_subprocess_exec`（stdin/stdout PIPE，
  stderr DEVNULL）；`NotImplementedError` → `MCP_TRANSPORT_ERROR`；紧凑 JSON +
  `\n` 后 drain；通知写完即返回；请求 `wait_for(readline)`；空行/EOF、>1 MiB、
  非法 JSON 为传输错误；id 不匹配时收集通知并继续读，否则协议错误；`close`
  关 stdin，等 2 秒，超时 kill 再 `wait`。
- `executable_errors` MCP 分支：`stdio` 只允许白名单 `command_alias`，禁止
  command/args；`streamable_http` 要求 http(s) endpoint。
- `GET /api/resources/mcp/stdio-aliases`，`resource:create`，位于 `/{rid:path}`
  之前。

## Windows / 子进程适配

- `McpStdioTransportTest` 在 `setUpClass` 将策略设为
  `WindowsProactorEventLoopPolicy`，生命周期测试实际拉起子进程，未 skip。
- 子进程额外设置 `cwd` 为仓库根、`PYTHONPATH`、`PYTHONUTF8=1` /
  `PYTHONIOENCODING=utf-8`：`-m tools.stats_service.stdio_server` 在 backend
  工作目录可导入 `tools`；Windows 默认 GBK stdout 否则会把工具中文 description
  打成非法 UTF-8。未改 Task 4 服务端。

## Self-review

- 未实现 Task 9，未替换 `run_mcp`。
- 简报列出修改 `session.py`，契约已满足故未改。
- Manifest 同时缺 alias 且带 command 时，两条错误都会 append；当前测试只断言
  含 `command_alias`。
- 子进程 env 注入超出简报字面 `create_subprocess_exec(*command, ...)`，否则
  Windows 生命周期测试无法绿。

## Files changed

Create:

- `backend/app/services/mcp/stdio_transport.py`

Modify:

- `backend/app/services/protocol.py` — MCP `executable_errors` stdio/http 分支
- `backend/app/api/resources.py` — `GET /mcp/stdio-aliases`
- `backend/tests/test_review_followup_a.py` — `McpStdioTransportTest`

Unchanged (listed in brief, not required):

- `backend/app/services/mcp/session.py`
