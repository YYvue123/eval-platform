# Task C4 报告：REAL03/06/07 模型、Agent、正式评测

## 状态

**DONE** — `tests.test_real_fill` 8 项 unittest 全部通过；未 commit；未写入 `backend/eval_platform.db`；单测未调用付费模型。

## RED

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_real_fill.RealFillTests.test_real03_06_07_blocked_without_l3_url tests.test_real_fill.RealFillTests.test_empty_api_url_health_invoke_not_pass -v
```

**关键输出：**

```
ImportError: cannot import name 'real03_models' from 'tools.real_fill.scenarios'
FAILED (errors=2)
```

**失败原因：** 测试已引用 `real03_models` / `real06_agent` / `real07_formal_task`，函数尚未实现（TDD 预期 RED）。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_real_fill -v
```

**结果：** `Ran 8 tests in 7.500s` — **OK**

| 用例 | 说明 |
| --- | --- |
| `test_isolated_url_is_not_business_db` | 既有隔离库断言 |
| `test_fill_client_login_admin` | 既有 FillClient 登录 |
| `test_real01_viewer_cannot_register` | 既有 REAL01 |
| `test_real02_dataset_import_returns_ids` | 既有 REAL02 |
| `test_real04_tools_parse_three_inputs_one_failed` | 既有 REAL04 |
| `test_real05_mcp_tools_call_success_and_empty_args_failed` | 既有 REAL05 |
| `test_real03_06_07_blocked_without_l3_url` | `L3_MODEL_API_URL` 删除或空串时 REAL03/06/07 均 `result==blocked`，`blocking_reason` 含 `missing L3_MODEL_API_URL`；ForbiddenClient 证明未 login、未打 API、未起 `stats_service` |
| `test_empty_api_url_health_invoke_not_pass` | 空 `api_url` 模型：health `ok=False`；invoke HTTP 400 且含 `model_api_url_required`，不标 pass |

GREEN 运行时 REAL01 仍会打出预期 `HTTPException ... status=403`；空 url invoke 为预期 400；另有 Starlette TestClient 既有 deprecation warning。

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `tools/real_fill/scenarios.py` | 新增 `_l3_url_present`、`real03_models`、`real06_agent`、`real07_formal_task` |
| `backend/tests/test_real_fill.py` | 新增缺 URL blocked 用例与空 `api_url` health/invoke 负例 |

未改动 models/agents/tasks API；未创建 commit。

## 自审

- [x] TDD：先测后码；RED 为 `cannot import name 'real03_models'`。
- [x] 隔离 TestClient；`from tests import isolated_env`。
- [x] `L3_MODEL_API_URL` 空/缺失立即 blocked；单测不启动 stats_service、不调用付费模型。
- [x] 空 `api_url` 禁止标 pass（health 非 ok；invoke 非 200）。
- [x] 返回 dict 不含 `api_url` / `api_key`；凭证用环境变量名 `L3_MODEL_API_KEY`（`credential_ref`），不把密钥写入证据。
- [x] REAL07 仅 `POST /api/tasks`（`trial_run=True`），不 INSERT 评分、不 dispatch runner。
- [x] REAL01–05 用例保留。
- [x] 测试从 `backend/` 运行。
- [x] 未 git commit；未写 `backend/eval_platform.db`。

## Review follow-up（Important：REAL06 不得用 tool.rejected 标 pass）

**问题：** `real06_agent` 曾用 `any(t.startswith("tool."))` 判定 tool loop，`tool.rejected` / `tool.failed` / `tool.selected` 也会 pass；Agent runtime 无法调用 HTTP parse 工具。

**修复：**

- 导出 `agent_events_count_as_tool_loop(types)`：仅当存在 `type == "tool.observed"` 为 True。
- L3 URL 空/缺失仍立即 blocked（不 login）。
- 登录后若 `parse_resource_id` 缺失：`blocked`，`blocking_reason` 含 `missing parse resource`。
- 有 parse id 时始终 `POST /api/resources/invoke`（body `{"text":"100 cm"}`），记录 `parse_correlation_id`。HTTP != 200 或 `body.status` 为 error/failed → `blocked` / `tool_invoke_failed`。
- Agent session/confirm/runs 在 L3 URL 存在时仍可执行；confirm 非 200 只记 `confirm_status`，不标 pass。
- pass 同时要求 invoke 成功 + `tool.observed`；返回不含 `api_url` / `api_key`。

**RED：** `cannot import name 'agent_events_count_as_tool_loop'`

**GREEN：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_real_fill -v
```

`Ran 10 tests in 7.925s` — **OK**（含 `test_agent_events_count_as_tool_loop`、`test_real06_missing_parse_resource_blocked`、`test_real03_06_07_blocked_without_l3_url`）。

未 commit；未写 `eval_platform.db`。

## 关注点

1. **单测只覆盖 blocked / 空 url 负例：** 有 `L3_MODEL_API_URL` 的 live 路径（health 一次、Agent session/confirm/runs、小样本 trial 任务）已写在 scenarios 中，但 unittest 故意不注入真实 URL，避免付费调用。
2. **REAL06 不宣称 pass 除非有真实工具循环：** 须 `POST /api/resources/invoke` 成功且事件含 `tool.observed`；`tool.rejected` 等不得 pass。
3. **REAL07 小样本：** 创建任务时 `trial_run=True`，不跑 TaskService，避免写评分与模型调用。
4. **ModelCreate 无 credential_ref 字段：** 创建时从环境变量名 `L3_MODEL_API_KEY` 解析密钥交给 API，description 只记引用名；返回值只含 `credential_ref` 字符串名。

## Review follow-up（Important：REAL06 pass 不依赖 tool.observed / confirm 200）

**问题：** Agent runtime 无法对 HTTP parse 发出 `tool.observed`。上一轮仍要求 `confirm_status==200` 且 `agent_events_count_as_tool_loop(types)`，live REAL06 即使 `resources/invoke` 成功也会 blocked。

**修复：**

- pass 条件：parse invoke 成功 **且** 模型有 `api_url`。
- 不要求 `tool.observed`，不要求 confirm 200。
- 证据字段仍记录 `confirm_status`、`run_id`、`parse_correlation_id`，以及 `agent_tool_observed=agent_events_count_as_tool_loop(types)`。
- 保留：L3 缺失立即 blocked（不 login）；缺 parse id → blocked；invoke 失败 → `tool_invoke_failed`；空 `api_url` → blocked；仅 `tool.rejected` 不得单独标 pass。

**RED：** `test_real06_pass_on_invoke_success_without_tool_observed` 期望 `pass`，实际 `blocked`。

**GREEN：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_real_fill -v
```

`Ran 13 tests in 7.942s` — **OK**。

未 commit。
