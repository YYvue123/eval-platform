# Task C3 报告：REAL04/05 工具与 MCP

## 状态

**DONE** — `tests.test_real_fill` 6 项 unittest 全部通过；未 commit；未写入 `backend/eval_platform.db`。

## RED

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_real_fill -v
```

**关键输出：**

```
ImportError: cannot import name 'real04_tools' from 'tools.real_fill.scenarios'
FAILED (errors=1)
```

**失败原因：** 测试已引用 `real04_tools` / `real05_mcp`，函数尚未实现（TDD 预期 RED）。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_real_fill -v
```

**结果：** `Ran 6 tests in 6.803s` — **OK**

| 用例 | 说明 |
| --- | --- |
| `test_isolated_url_is_not_business_db` | `DATABASE_URL` 经 `assert_isolated_database`，文件名不是业务库 `eval_platform.db` |
| `test_fill_client_login_admin` | 既有 FillClient 登录 |
| `test_real01_viewer_cannot_register` | 既有 REAL01 |
| `test_real02_dataset_import_returns_ids` | 既有 REAL02 |
| `test_real04_tools_parse_three_inputs_one_failed` | `stats_service` 随机端口；注册 parse+stats；parse 三次调用中一次 failed；返回 resource_id 与 3 个 correlation_id |
| `test_real05_mcp_tools_call_success_and_empty_args_failed` | 注册 MCP `{base}/mcp`；`tools/call` 成功；空 arguments 失败（`ok=False`）；调用历史含 success/failed |

GREEN 运行时 REAL01 仍会打出预期 `HTTPException ... status=403`；另有 Starlette TestClient 既有 deprecation warning。

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `tools/real_fill/scenarios.py` | 新增 `real04_tools`、`real05_mcp` |
| `backend/tests/test_real_fill.py` | 新增 REAL04/05 用例；`stats_service` 子进程 |

未改动 resources/MCP API；未创建 commit。

## 自审

- [x] TDD：先测后码；RED 为 `cannot import name 'real04_tools'`。
- [x] 隔离 TestClient；`from tests import isolated_env`。
- [x] `tests.followup_helpers.stats_service` 随机端口，未写死端口。
- [x] 未发明端点：`POST /api/resources/register`、`POST /api/resources/invoke`、`POST /api/resources/mcp/probe`。
- [x] Manifest 复用 `followup_helpers.tool_manifest`（A wizard 形状）。
- [x] 未调用付费模型。
- [x] 测试从 `backend/` 运行。
- [x] 未 git commit；未写 `backend/eval_platform.db`。

## 关注点

1. **REAL04 只 invoke parse：** 简报要求注册 parse+stats，三次输入打 parse；stats 仅注册，供后续 REAL06 等复用 ID。
2. **无效输入：** 第三次 body 为 `{}`（缺 `text`），网关信封 `body.status` 为 `error`，调用历史记 `failed`。
3. **REAL05 选择注册后再 probe：** 简报允许 register 或 probe；注册后 `resource_id` 互斥于 adhoc `endpoint`，调用历史挂在已注册 MCP 上，便于证据 ID。
4. **空 arguments：** `tools/call` `parse_measurements` + `arguments: {}` → probe `ok=False`（与 A 的 `MCP_TOOL_ERROR` / isError 路径一致）。
