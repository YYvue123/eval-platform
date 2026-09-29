# 评审跟进总路线图与子项目 A 设计

日期：2026-09-29。依据：`docs/review-followup-2026-09-28/`（R01–R12、02 前端规格、03 真实数据方案、04 执行任务书）。
基线：`380650893eb44871e4722100c8060def66619d56` + 分支 `fix/review-followup-d1` 上未提交的 D1/D2 改动（用户决定暂不提交）。

## 1. 当前状态

已由前两轮会话处理并有隔离测试（`tests/test_review_followup_d1.py`、`tests/test_review_followup_d2.py`）：

| 评审项 | 状态 |
|---|---|
| R01 向导缺 idempotent | 已修：结构检查按完整契约，返回上一步作废检查结论 |
| R02 副作用异常/stub 成功 | 已修：blocked/denied，不写 success 与幂等成功 |
| R03 资源全链路对象隔离 | 已修：详情/匹配/注册中心/调用/探测/健康/心跳/下线/事件 |
| R04 影子构造评分 | 已修为明确 blocked（真实双版本影子留给子项目 C） |
| R05 Agent 工具消息历史 | 已修：完整 assistant.tool_calls 与 tool_call_id |
| R06 Agent 终态推断 | 已修：last_run_id / task_status / report_status / recent_runs |
| R07 可执行配置 | 部分：禁止 local://，Skill 必须有 chain；**Skill 步骤仍绕过网关** |
| R08 结构≠成功 | 已修：HTTP 必须明确 status=success；MCP 协议错误 ok=false |
| R09 凭证与证据 | 部分：明文凭证拒绝入库、credential_ref；**调用日志缺脱敏输入输出证据，无历史 API，probe 不落库** |
| R10 演练证据 | 已修：BACKUP_DIR 真实文件 + 摘要 + 当前登录人签署 |
| R11 表单/全站 | 未做：SchemaForm 有损；全站页面属于子项目 D |
| R12 版本冻结 | 已修：同版不同内容 409，调用读冻结快照 |

另有遗留：`tests/test_eval_flow` 两条 `database is locked`；`tests/isolated_env.py` 使用 `setdefault`，外部已设置的 `DATABASE_URL` 会让测试指向业务库。

## 2. 总路线图

按 A → B → C → D 执行，每个子项目独立出实施计划、独立验收。

| 子项目 | 范围 | 退出门禁 |
|---|---|---|
| A. D2 核心体验收尾 | R07/R09/R11 剩余、MCP 完整协议与工作台、自建统计工具服务、测试隔离加固 | 纯表单注册并真实调用自建 HTTP 工具、两步 Skill、自建 MCP（HTTP 与 stdio）；调用记录可按资源回查；全量隔离回归通过 |
| B. D4 业务库 Mock 清理 | 03 的 C0/C1：plan/apply/verify 管理脚本、一致性备份与恢复实测、清单与 hash、衍生链处理、防 seed 回灌 | plan 不写库；目标或清单 hash 失配 apply 拒绝；恢复实测；simulation/provider=mock/stub 结构标志清零；重启不回灌 |
| C. D5 真实数据填充 | REAL01–12：.env 模型、自建工具/MCP/Skill、Agent、正式评测、提示词实验、基准/安全、榜单/服务、影子、运维 | 真实结果进入已确认的业务库并刷新可见；失败保留；七天窗口与专家签署标 blocked |
| D. D3 全站 24 页 | 02 的页面矩阵与公共框架 | 各页适用六态、服务端分页、1440/1024/390、明暗主题、键盘；截图证据 |

依赖：C 需要 A 的可执行工具与 MCP，需要 B 先清除 Mock；D 可与 B/C 并行，但真实数据到位后再做最终验收。

## 3. 子项目 A 设计

### A0 测试隔离加固

`tests/isolated_env.py` 改为强制赋值：已有 `DATABASE_URL` 只有在其 SQLite 文件解析后位于 `backend/tests/_isolated/` 内时才保留（兼容 `run_isolated_tests.py`、e2e、L3 脚本各自的隔离库），否则覆盖为 `_isolated/wp00_test.db`。同时导出 `assert_isolated_database(url)`，导入时即对最终值断言；非 SQLite URL 一律拒绝。UPLOAD_DIR/LOG_DIR/BACKUP_DIR 同规则。历史脚本 `docs/implementation-plan-2026-09-28/verification/run_isolated_tests.py` 的库在 `_isolated` 外，新规则下会回落到 `_isolated/wp00_test.db`（仍不触碰业务库）。

`test_eval_flow` 的 `database is locked` 已复现并定位（`docs/superpowers/eval_flow_baseline.log`）：`api/tasks.py` 的 `run_task` 与 `retry_task_api` 在 `commit` 并登记后台 `dispatch_queue` 之后，又用请求会话 `log_audit` 写入；FastAPI 0.141 / Starlette 1.6 的后台任务在发送响应时、`get_db` 提交之前执行，请求会话持有 SQLite 写锁，后台 `recover_expired_leases` 等满 60 秒超时。修复：所有写入（含审计）提交后再登记后台任务；`api/agents.py` 两处同类路径一并调整。另一条失败 `test_model_mapping_acl_and_scene` 期望未配置 api_url 的模型调用成功（Mock 回退），与“禁止 Mock”冲突，改为断言 400 `model_api_url_required`，不删除该用例。

### A1 Skill 步骤经授权网关

`run_skill` 改为 async，并接收 `step_invoker` 回调。网关调用 Skill 时传入闭包：每一步以同一 actor、父 trace、派生 correlation（`{parent_cid}:{step_id}`）递归调用 `invoke_tool`，因此每步都经过对象 ACL、冻结版本、副作用检查、幂等与 `ResourceCallLog`。约束：

- 步骤不得引用 `resource_type=skill` 的资源（拒绝嵌套，避免递归环）；网关以 `_depth` 参数兜底，超过 1 抛错。
- 任一步响应 `header.status != success`：Skill 整体失败，错误信息指出 step_id 与步骤错误码；已完成步骤的输出保留在失败信息中。
- 步骤输出取 `response_result(envelope)`，`$ref` 解析规则不变。
- 汇总 `passed/score` 仅在步骤结果含这些字段时计算；统计类工具没有 score 时 `score=None`，不补 0。

### A2 调用证据与历史

`ResourceCallLog` 新增 `input_digest`（脱敏 JSON，截断 4000 字符）、`output_digest`（同）、`input_hash`、`output_hash`（sha256）、`source`（`gateway` / `skill_step` / `mcp_probe`）、`parent_correlation_id`。已有列的迁移沿用 `init_db` 中的 `ALTER TABLE` 列表。脱敏复用 `api/resources.py::_redact_manifest` 的键规则，抽到 `services/redaction.py`。

新增 `GET /api/resources/calls/{rid:path}?page&page_size&status`（`rid` 含 `/`，因此资源 ID 放在路径末尾）：先 `_visible_resource` 校验对象，再按 resource_id 且 `tenant_id == actor.tenant_id` 分页（内置资源同样按调用者租户过滤，互不可见）。复用 `resource:view`，不新增权限码。该路由与 `mcp/stdio-aliases` 都必须声明在 `/{rid:path}` 通配路由之前。

`mcp/probe` 对已注册资源写 `ResourceCallLog(source="mcp_probe")`；临时 endpoint 探测写到 `resource_id="adhoc-mcp:<host>"`，tenant/user 同样记录，token 不进 digest。

前端试用台与 MCP 工作台的“最近调用”改读该接口。

### A3 无损 SchemaForm

- `integer` 独立 kind：`el-input-number` `:step="1" :precision="0"`，校验 `Number.isInteger`。
- `minimum/maximum/exclusiveMinimum/exclusiveMaximum/minLength/maxLength/pattern/format(email,uri,date)` 校验。
- `default` 在挂载和 schema 变化时写入尚未赋值的字段（不覆盖用户已输入值）。
- array/object：textarea 保留原文 `drafts[key]`；JSON 非法时不更新 modelValue，字段下显示 `JSON 第 N 行: 错误`，`validate()` 返回该字段错误；合法时写入对象。
- 不支持的构造（`oneOf/anyOf/allOf/$ref`、嵌套 object 的 properties）显示“此字段请用高级 JSON 编辑”，仍以 JSON 编辑，不丢失。
- `validate()` 返回 `{ ok, missing, errors: {key: message} }`，调用方同时展示。
- 纯函数抽到 `frontend/src/utils/schemaForm.js`（`buildFields`、`applyDefaults`、`validateValue`），用 Node 自带 `node --test` 测试，不引入新依赖。

### A4 MCP 完整实现

后端 `services/mcp/` 包（替换 `mcp_client.py`；旧模块只被 `skill_runtime.py` 与一条 AsyncMock 单测 `RemoteMcpClientTest` 使用，删除旧模块并由真实子进程传输测试取代该单测）：

- `http_transport.py`：Streamable HTTP。POST 带 `Accept: application/json, text/event-stream`、`MCP-Protocol-Version`；响应 `application/json` 直接解析，`text/event-stream` 逐事件解析直到拿到匹配 id 的响应，期间收集通知与 `id:` 作为 last_event_id；流在响应前中断且有 last_event_id 时，GET 同 endpoint 带 `Last-Event-ID` 续读一次。会话：initialize 响应头 `Mcp-Session-Id` 保存并在后续请求携带；404 视为会话过期（`MCP_SESSION_EXPIRED`）；结束时 DELETE（405 忽略）。
- `stdio_transport.py`：仅允许 `MCP_STDIO_ALLOWLIST` 环境变量中的别名（JSON：`{"alias": ["绝对路径可执行文件", "参数"...]}`）。Manifest 用 `interfaces.transport="stdio"` 与 `interfaces.command_alias`，不接受任意命令。`asyncio.create_subprocess_exec`，换行分隔 JSON-RPC，stderr 重定向到 DEVNULL（避免管道写满阻塞子进程），单条消息上限 1 MiB；事件循环不支持子进程（Windows Selector 循环）时返回 `MCP_TRANSPORT_ERROR` 并说明原因，超时后 kill 并回收进程。
- `session.py`：`McpSession(transport)` 提供 `open()`（initialize → 校验 protocolVersion → `notifications/initialized`）、`list_tools()`（跟随 `nextCursor` 分页，最多 20 页）、`call_tool(name, arguments)`、`close()`，以及 `notifications` 列表。收到 `notifications/tools/list_changed` 置 `catalog_changed=True`。
- 错误归一 `McpError(code, message)`：`MCP_PROTOCOL_ERROR`（JSON-RPC error）、`MCP_TOOL_ERROR`（result.isError）、`MCP_AUTH_FAILED`（401/403）、`MCP_TIMEOUT`、`MCP_SESSION_EXPIRED`、`MCP_TRANSPORT_ERROR`、`MCP_STDIO_NOT_ALLOWED`。
- 目录快照：每次成功 `tools/list` 计算目录 hash，写 `ResourceEvent(event_type="mcp.catalog", payload={hash, count, tool_names})`；与上一快照不同或收到 list_changed 时写 `mcp.catalog_changed`。`GET /resources/{rid}` 输出 `mcp_catalog: {hash, count, observed_at, stale}`，stale 表示最近一次观测晚于该快照出现过 changed 事件。
- `run_mcp` 改为每次调用开一个会话：open → 目标方法 → close；网关对 `tools/call` 的 `isError` 抛 `McpError`，从而记为 failed，不再外包 success。
- `mcp/probe` 返回 `{ok, mode, target, transport, session: {protocol_version, server_info, session_id_present}, error: {code, message} | null, result, notifications}`。

前端 MCP 工作台（在现有对话框基础上）：

- 状态条五步：未配置 → 结构有效 → 已协商（显示协议版本、服务器名）→ 已发现 N 个工具 → 最近调用成功/失败；任一步失败后续步骤回到“未执行”。
- 工具目录可搜索；显示 stale 标签与“重新获取”。
- 选择工具后用 A3 的 SchemaForm 生成参数表单。
- 错误按 code 映射恢复指引（认证失败→检查凭证引用；超时→检查服务是否启动；会话过期→重新连接；工具错误→查看工具返回内容）。
- 向导 MCP 分支增加传输方式选择：Streamable HTTP / stdio（stdio 下拉只列服务端返回的允许别名，接口 `GET /api/resources/mcp/stdio-aliases`，复用 `resource:create`）。
- “最近调用”读 A2 接口。

### A5 自建统计服务 `tools/stats_service`

仓库根新增 `tools/stats_service/`（独立包，复用 backend 的 venv，依赖仅 fastapi/uvicorn/pydantic）：

- `core.py`：`parse_measurements(text)` 从文本中提取“数值+单位”；`compute_stats(values: list[{value: float, unit: str}], target_unit: str | None)`。支持长度（mm/cm/m/km）、质量（mg/g/kg）、时间（ms/s/min/h）三类；混合量纲、未知单位、非有限数报错；返回 count/sum/mean/min/max/variance（总体方差）/unit/dimension/converted。无样例硬编码。
- `app.py`：FastAPI。`GET /health`；`POST /v1/parse` 与 `POST /v1/stats` 接收平台信封（`body.parameters`）或裸参数，返回 `{"status": "success", "result": {...}}`，输入错误返回 HTTP 200 + `{"status": "error", "error": {...}}`（验证平台对业务错误的识别）；`POST /mcp` 实现 Streamable HTTP 服务端（initialize 返回 `Mcp-Session-Id`；`tools/list` 分页每页 1 个工具，共 `parse_measurements`、`compute_stats` 两个工具，用来验证游标；`tools/call` 输入错误返回 `isError: true`；请求 `Accept` 含 `text/event-stream` 且 `params._meta.stream=true` 时以 SSE 返回；`_meta.announce_list_changed=true` 在响应前推送 `notifications/tools/list_changed`；`_meta.drop_before_response=true` 在响应前断流，响应留待 `GET /mcp` + `Last-Event-ID` 续读；`DELETE /mcp` 结束会话）。这些 `_meta` 开关是自建服务的协议测试入口，行为真实发生，不是替身。
- 两步 Skill：`parse`（text → values）→ `stats`（values → 统计），第二步 `values` 绑定 `s1.output.values`。
- `stdio_server.py`：同一组 MCP 方法的 stdio 版本（`python -m stats_service.stdio_server`）。
- 绑定 `127.0.0.1:8765`，启动脚本 `tools/stats_service/run.ps1`。
- 测试 `tools/stats_service/tests/test_core.py`、`test_mcp.py`，以及后端 `tests/test_review_followup_a.py` 中用真实子进程启动 8765 的集成测试（端口占用时改用随机空闲端口）。
- 文档中声明：这是自建本地 MCP 实测，不代表公共服务互操作验收。

### 交叉约束

- 测试全部经 `tests/isolated_env.py`；不指向业务 `eval_platform.db`。
- 前端改动后运行 `npm run collect-permissions`、`npm run verify:ux-static`、`npm run build`。本子项目的新接口复用 `resource:view` / `resource:create` / `resource:invoke`；如实现中出现新动作，同批完成 AGENTS.md 权限流程。
- 不修改业务库、不调用付费模型。
- 当前未提交改动保留；本子项目仍不提交，除非用户另行指示。

## 4. 子项目 A 验收

| 用例 | 断言 |
|---|---|
| A-REV07a | 两步 Skill（文本解析→数值统计）每步产生 source=skill_step 调用日志，parent_correlation_id 一致；第二步真实消费第一步输出 |
| A-REV07b | Skill 引用另一租户私有工具 → 整体失败且错误指向该步骤；引用 Skill → 注册或执行被拒 |
| A-REV08 | 自建工具 HTTP 200 + status=error → failed；MCP isError → failed；session 过期 → MCP_SESSION_EXPIRED |
| A-REV09 | 调用历史接口分页、跨租户 404；digest 中无 credential 原文；probe 落库 |
| A-REV11 | integer 保持整数；非法 JSON 保留原文并报错；default 初始化；enum/description 不丢 |
| A-MCP | HTTP：initialize→initialized→tools/list 两页→tools/call 成功与 isError；SSE 响应；Last-Event-ID 续读；stdio 允许别名成功、非白名单拒绝 |
| A-ISO | 预设业务 DATABASE_URL 时导入 isolated_env 后被覆盖；指向 `_isolated` 外的 sqlite 断言失败 |
| A-FULL | 全量隔离回归通过，`test_eval_flow` 无 database is locked |
| A-UI | 浏览器实操：纯表单注册自建 HTTP 工具与 MCP，完成真实调用，刷新后最近调用仍在；1440/390 宽度截图 |
