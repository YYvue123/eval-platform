# 子项目 A 验收证据

日期：2026-09-29。工作目录：`E:\eval-platform`。未提交。未触碰 `backend/eval_platform.db`。

## 环境

- HEAD：`380650893eb44871e4722100c8060def66619d56`（`Deliver frontend UX U0-U5 no-mock hardening with smoke e2e.`）
- 工作树：相对 HEAD 有子项目 A 未提交改动（见文末 `git status --short` 摘要）
- 隔离库：`sqlite+aiosqlite:///E:/eval-platform/backend/tests/_isolated/a_ui.db`
- 上传/日志/备份：`backend/tests/_isolated/a_ui_{uploads,logs,backups}`
- 登录：`admin` / `admin123`（隔离 UI 开发引导账号）
- 自建统计服务：`http://127.0.0.1:8765`（`tools/stats_service/run.ps1`）
- 隔离后端：`127.0.0.1:8001`（本机 `8000` 已被既有栈占用，未复用、未结束他人进程）
- 隔离前端：`http://127.0.0.1:5174`（Vite 配置 `frontend/vite.a-ui.config.js`，`/api` 代理到 8001；`5173` 同理未占用）
- `MCP_STDIO_ALLOWLIST`：别名 `stats-local` → `.venv\Scripts\python.exe -m tools.stats_service.stdio_server`

## 本轮回归修复

Skill 向导步骤工具下拉曾只请求 `status=online`，已注册 HTTP 工具（`registered`）不可选。改为 `isInvocableTool`（`online` / `pending` / `registered`）。单测：`isInvocableTool includes registered HTTP tools, not only online`。

Task 14 复审（Needs fixes）产品文案：`Resources.vue` 页眉曾写研发口号「真实调用，无 Mock 假成功。」（证据曾误记该口号抽检通过，不成立）。已改为操作说明「发现、注册并试用工具 / Skill / MCP；调用结果与最近记录在试用台查看。」详情抽屉 Alert 改为「版本时间线尚未接入本页；调用记录请打开试用台查看。」未改 `Agents.vue` / `Models.vue`（Models 仍保留 verify-ux-static 所需的 Mock 接入句）。`npm run verify:ux-static` OK。

---

## A-REV07a

- Result: pass
- Environment: isolated `a_ui.db` + `tests.test_review_followup_a.TestSkillGateway`
- Worktree: HEAD `3806508` + 未提交 A 改动
- Resource IDs: `demo/skill_ui`（Skill）、`demo/parse_ui`（s1）、`demo/stats_ui`（s2）
- Correlation / trace IDs:
  - 父：`trial-1790623722560`，`trace_id=21765b913c1c463192b94f5d644faa6f`
  - s1：`trial-1790623722560:s1`，`source=skill_step`，`parent_correlation_id=trial-1790623722560`
  - s2：`trial-1790623722560:s2`，`source=skill_step`，同一 parent / trace
- Assertions:
  - 试用输入 `{"text":"100 cm, 2 m, 500 mm","target_unit":"m"}`
  - `converted=[1.0, 2.0, 0.5]`
  - `mean=1.1666666666666667`，与 `3.5/3` 误差为 0（`< 1e-9`）
  - `GET /api/resources/calls/{rid}` 两工具均可见 `skill_step`（试用台历史表**无** `source` 列，不能从 UI 截图读出 `skill_step`）
- API excerpt（脱敏 digest，非截图 pass）：
```json
{"resource_id":"demo/parse_ui","id":8,"source":"skill_step","parent_correlation_id":"trial-1790623722560","correlation_id":"trial-1790623722560:s1","output_digest":"{\"result\":[{\"unit\":\"cm\",\"value\":100.0},{\"unit\":\"m\",\"value\":2.0},{\"unit\":\"mm\",\"value\":500.0}]}"}
{"resource_id":"demo/stats_ui","id":9,"source":"skill_step","parent_correlation_id":"trial-1790623722560","correlation_id":"trial-1790623722560:s2","output_digest":"{\"converted\":[1.0,2.0,0.5],\"count\":3,\"mean\":1.1666666666666667,\"sum\":3.5,\"unit\":\"m\"}"}
{"resource_id":"demo/skill_ui","id":10,"source":"gateway","correlation_id":"trial-1790623722560","output_digest":"result.converted=[1.0,2.0,0.5], result.mean=1.1666666666666667"}
```
- Screenshots: `a-ui-skill-trial-1440.png`（结果列常被裁切；**converted / mean / skill_step 以 calls API 为准，不视为截图通过**）
- Blocking reason: —

## A-REV07b

- Result: pass
- Environment: `tests.test_review_followup_a`（跨租户历史分区、嵌套 Skill 注册/运行拒绝）
- Worktree: 同上
- Resource IDs: 测试夹具（非 UI）
- Correlation / trace IDs: 见定向套件输出
- Assertions: `test_builtin_history_is_partitioned_by_calling_tenant`；`test_registration_enforces_acl_and_rejects_nested_skill`；`test_historical_nested_manifest_is_rejected_at_runtime`
- Screenshots: 未要求 UI
- Blocking reason: —

## A-REV08

- Result: pass
- Environment: isolated UI + 后端定向测试
- Worktree: 同上
- Resource IDs: `demo/parse_ui`；MCP `demo/mcp_http_ui`
- Correlation / trace IDs:
  - HTTP 缺参失败（本轮复拍）：`trial-1790624471758`，`trace_id=254b863d78a84ec2b900437dbbed155c`，`source=gateway`，`status=failed`，`input_digest={}`
  - HTTP 缺参失败（此前）：`trial-1790623292885`，`trace_id=c48ae9b3416f4723a78a5a687f8607dd`，`source=gateway`，`status=failed`
  - MCP 空 `values`：`correlation_id=66a9aac6-a3ef-4902-b95c-4a7894d4d678`，`trace_id=73db2da697ff413398096c65a808abb1`，`source=mcp_probe`，`status=failed`，界面 `MCP_TOOL_ERROR：样本不能为空`，五步条「最近调用失败」
- Assertions: 缺 `text` 不出现绿色成功；MCP `ok=false` 不弹成功 toast；会话过期等见 `tests.test_review_followup_a`
- Screenshots: `a-ui-parse-fail-1440.png`；**已替换** `a-ui-parse-fail-390.png`（~390 试用台：高级 JSON `{}` + 结果 `TOOL_EXEC_FAILED` + 最近调用 `failed`，**不是**详情抽屉）; `a-ui-mcp-http-tool-error-1440.png`
- Blocking reason: —

## A-REV09

- Result: pass
- Environment: isolated UI 历史 + `GET /api/resources/calls/{rid}` + 后端脱敏/分页测试
- Worktree: 同上
- Resource IDs: `demo/parse_ui` 刷新后再开试用台仍 **4** 条（本轮新增缺参失败后）
- Correlation / trace IDs: 成功试用 `trial-1790623255788` / `1afd04c05083461f97e4138830bd3d76`；skill_step 行见 A-REV07a
- Assertions: 刷新后历史仍在（UI 可见 failed/success 行与 trace）；digest 为脱敏 JSON；`input_hash`/`output_hash` 存在；MCP 探测写入 `source=mcp_probe`。**试用台表格不展示 `source`，无法在截图中标出 `source=skill_step`。**
- API excerpt（`GET /api/resources/calls/demo%2Fparse_ui`）：
```json
[
  {"source":"gateway","parent_correlation_id":"","status":"failed","correlation_id":"trial-1790624471758","trace_id":"254b863d78a84ec2b900437dbbed155c"},
  {"source":"skill_step","parent_correlation_id":"trial-1790623722560","status":"success","correlation_id":"trial-1790623722560:s1","trace_id":"21765b913c1c463192b94f5d644faa6f"},
  {"source":"gateway","parent_correlation_id":"","status":"failed","correlation_id":"trial-1790623292885","trace_id":"c48ae9b3416f4723a78a5a687f8607dd"},
  {"source":"gateway","parent_correlation_id":"","status":"success","correlation_id":"trial-1790623255788","trace_id":"1afd04c05083461f97e4138830bd3d76"}
]
```
- Screenshots: **已替换** `a-ui-parse-history-refresh-1440.png`；**新增** `a-ui-parse-history-3-1440.png`（同一画面：最近调用 4 行 failed/success/failed/success，含 Skill 后的 105 ms success 行）。旧图只有 2 行，不能当作「Skill 后 3 行」证据。`source=skill_step` **仅 API**。
- Blocking reason: —

## A-REV11

- Result: pass
- Environment: `frontend/tests/unit/schemaForm.test.mjs`（及 SchemaForm 组件）
- Worktree: 同上
- Resource IDs: —
- Correlation / trace IDs: —
- Assertions: integer 不映射为 number；required 填值后错误清除；嵌套/组合走高级 JSON
- Screenshots: UI 可选；本轮以单测为准
- Blocking reason: —

## A-MCP

- Result: pass
- Environment: `tests.test_review_followup_a` MCP 段 + 浏览器工作台
- Worktree: 同上
- Resource IDs: `demo/mcp_http_ui`（`http://127.0.0.1:8765/mcp`）、`demo/mcp_stdio_ui`（别名 `stats-local`）
- Correlation / trace IDs:
  - HTTP 成功 `tools/call` parse：`cb7af7959ebb495bbd0fbde86fe8947f`
  - HTTP 空样本失败：见 A-REV08
  - stdio parse 成功（本轮复拍）：`trace_id=7b8bf485b76b448ab8be93d065f9a7cc`，`correlation_id=3d1e34b3-2def-4f92-a9cc-8fb517b43b9c`，`source=mcp_probe`，`status=success`，`arguments.text=100 cm, 2 m`
  - stdio parse 成功（此前）：`cae7815562f445dd98243822c18054d4`
- Assertions:
  - 协商 `2024-11-05` · 服务器名 `stats-service`
  - `tools/list` 聚合 2 个工具：`parse_measurements`、`compute_stats`
  - stdio 仅别名选择，DOM `hasCmdInput=false`（无自由 command 输入）
  - SSE / Last-Event-ID / 未知别名拒绝：后端测试
- Screenshots: **已替换** `a-ui-mcp-http-listed-1440.png`（五步条：已协商 `2024-11-05 · stats-service` + **最近调用失败**）；`a-ui-mcp-http-tool-error-1440.png`（`MCP_TOOL_ERROR：样本不能为空` + 最近调用失败）；**已替换** `a-ui-mcp-stdio-listed-1440.png` 与新增 `a-ui-mcp-stdio-call-1440.png`（parse 调用后：最近调用成功，非预填表单）。默认横向步骤条会被截图工具裁掉第五步，复拍时对 `.mcp-steps` 临时改为纵向排列以便五步同框（产品默认仍为横向换行）。`a-ui-mcp-stdio-alias-wizard-1440.png` 未重拍。
- Blocking reason: —

## A-ISO

- Result: pass
- Environment: `tests.test_isolation_guard`（4 用例）：接受 `_isolated` 路径；拒绝相对业务库 URL；拒绝非 SQLite
- Worktree: 同上
- Resource IDs: —
- Correlation / trace IDs: —
- Assertions: 测试导入强制 `assert_isolated_database`；本轮未把 `DATABASE_URL` 指到 `eval_platform.db`
- Screenshots: —
- Blocking reason: —

## A-FULL

- Result: pass
- Environment: `backend` `.venv` unittest discover；前端 unit / permissions / ux-static / build
- Worktree: 同上
- Resource IDs: —
- Correlation / trace IDs: —
- Assertions:
  - 定向：`tests.test_isolation_guard` + `test_review_followup_a` + `test_review_followup_d1` + `test_review_followup_d2` + `test_tool_gateway` + `test_agent_runtime` + `test_ops_governance` → **Ran 81 tests in 75.696s OK**
  - 全量：`python -m unittest discover -s tests -p "test_*.py" -v` → **Ran 208 tests in 157.301s OK**；输出无 `database is locked`
  - 前端（本轮复核）：`npm run test:unit` → **# tests 34 / # pass 34 / # fail 0**
  - `npm run collect-permissions` → **55 个权限码**，无新增 `resource:*` 动作
  - `verify:ux-static` OK（复审文案修改后再跑：`routes sampled=20 nav=13 warnings=0`）；`build` 约 18s（本 Task 14 前半段）
- Screenshots: —
- Blocking reason: —

## A-UI

- Result: pass
- Environment: 浏览器 `http://127.0.0.1:5174/resources`，cursor-ide-browser
- Worktree: 同上
- Resource IDs: `demo/parse_ui`、`demo/stats_ui`、`demo/skill_ui`、`demo/mcp_http_ui`、`demo/mcp_stdio_ui`
- Correlation / trace IDs: 见 A-REV07a / A-REV08 / A-MCP
- Assertions: HTTP 试用成功与业务失败；两步 Skill 数值；MCP HTTP 五步条与失败第五步；MCP stdio 目录+调用成功；无任意 command 框
- Screenshots:
  - 1440：`a-ui-parse-trial-1440.png`、`a-ui-parse-fail-1440.png`、`a-ui-parse-history-refresh-1440.png`、`a-ui-parse-history-3-1440.png`、`a-ui-stats-trial-1440.png`、`a-ui-skill-trial-1440.png`、`a-ui-mcp-http-listed-1440.png`、`a-ui-mcp-http-tool-error-1440.png`、`a-ui-mcp-stdio-listed-1440.png`、`a-ui-mcp-stdio-call-1440.png`、`a-ui-mcp-stdio-alias-wizard-1440.png`
  - ~390：`a-ui-parse-fail-390.png`（试用台缺参失败，非详情抽屉）、`a-ui-parse-trial-390.png`、`a-ui-resources-390.png`
- Blocking reason: —

## 截图索引

| 文件 | 说明 |
|---|---|
| `a-ui-parse-trial-1440.png` | parse 试用成功 |
| `a-ui-parse-fail-1440.png` | 缺参业务失败（宽屏） |
| `a-ui-parse-fail-390.png` | ~390 试用台：空 JSON `{}`、执行失败、最近调用 `failed` |
| `a-ui-parse-history-refresh-1440.png` / `a-ui-parse-history-3-1440.png` | 试用台最近调用 4 行（Skill 后 3 行 + 本轮复拍缺参失败）；无 source 列 |
| `a-ui-parse-trial-390.png` | 窄屏试用+历史 |
| `a-ui-resources-390.png` | 窄屏工具中心 |
| `a-ui-stats-trial-1440.png` | stats HTTP 试用 |
| `a-ui-skill-trial-1440.png` | 两步 Skill 试用 |
| `a-ui-mcp-http-listed-1440.png` | HTTP MCP 五步条（协议版本 + 最近调用失败）；纵向排版以便同框 |
| `a-ui-mcp-http-tool-error-1440.png` | `MCP_TOOL_ERROR` + 最近调用失败 |
| `a-ui-mcp-stdio-listed-1440.png` / `a-ui-mcp-stdio-call-1440.png` | stdio 工作台：已协商 + 已发现 2 工具 + **最近调用成功** |
| `a-ui-mcp-stdio-alias-wizard-1440.png` | stdio 仅别名（无 command 框） |

## 产品文案抽检

- **不得记为通过**：旧口号「真实调用，无 Mock 假成功。」
- **Resources.vue 现文案**：页眉「发现、注册并试用工具 / Skill / MCP；调用结果与最近记录在试用台查看。」详情 Alert「版本时间线尚未接入本页；调用记录请打开试用台查看。」
- 未改 `Agents.vue` / `Models.vue`。`verify:ux-static` OK（55 权限码）。

## git 检查（Step 9）

`git diff --check`：无 whitespace error。工作副本提示 `backend/app/database.py` CRLF→LF（既有换行，非本任务引入的 diff 错误）。

未把业务库、明文 token、运行日志、`__pycache__` 列入证据。隔离进程（8765 / 8001 / 5174）本轮启动，未结束 8000 / 5173。
