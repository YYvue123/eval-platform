# Task C5 报告：REAL08–12

## 状态

**DONE** — `tests.test_real_fill` 19 项 unittest 全部通过；未 commit；未写入 `backend/eval_platform.db`；未伪造专家签署或回填七天影子窗口。

## RED

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_real_fill.RealFillTests.test_real08_blocked_without_l3_url tests.test_real_fill.RealFillTests.test_real09_never_signed_and_skips_expert_paths tests.test_real_fill.RealFillTests.test_real10_4xx_publish_is_pass tests.test_real_fill.RealFillTests.test_real10_missing_publish_endpoint_blocked tests.test_real_fill.RealFillTests.test_real11_blocked_seven_day_window tests.test_real_fill.RealFillTests.test_real12_backup_200_isolated tests.test_real_fill.RealFillTests.test_real03_06_07_blocked_without_l3_url -v
```

**关键输出：**

```
ImportError: cannot import name 'real08_prompts' from 'tools.real_fill.scenarios'
FAILED (errors=7)
```

**失败原因：** 测试已引用 `real08_prompts` / `real09_safety` / `real10_leaderboard` / `real11_shadow` / `real12_ops`，函数尚未实现（TDD 预期 RED）。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_real_fill -v
```

**结果：** `Ran 19 tests in 9.577s` — **OK**

| 用例 | 说明 |
| --- | --- |
| 既有 REAL01–07 及相关负例 | 全部保留并通过 |
| `test_real08_blocked_without_l3_url` | 无 `L3_MODEL_API_URL` 时 `result==blocked`，`blocking_reason` 含 `missing L3_MODEL_API_URL`；ForbiddenClient 证明未 login |
| `test_real03_06_07_blocked_without_l3_url` | 同步覆盖 REAL08 缺 URL |
| `test_real09_never_signed_and_skips_expert_paths` | RecordingClient 路径不含 sign/approve/expert；返回不得 `signed=True`；隔离 TestClient 再跑一遍 |
| `test_real10_4xx_publish_is_pass` | 无合格正式结果时 publish 4xx → `result==pass` |
| `test_real10_missing_publish_endpoint_blocked` | 404 → `blocking_reason` 含 `endpoint_missing` |
| `test_real11_blocked_seven_day_window` | `result==blocked`，原因含「七天」或 seven；未调 shadow/promote |
| `test_real12_backup_200_isolated` | `POST /api/ops/backup` 200；路径落在隔离 `BACKUP_DIR`；库名不是 `eval_platform.db` |

GREEN 运行时 REAL01 仍会打出预期 `HTTPException ... status=403`；空 url invoke 为预期 400；另有 Starlette TestClient 既有 deprecation warning。

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `tools/real_fill/scenarios.py` | 新增 `real08_prompts`、`real09_safety`、`real10_leaderboard`、`real11_shadow`、`real12_ops` |
| `backend/tests/test_real_fill.py` | 新增 REAL08–12 用例；缺 L3 用例纳入 REAL08 |

未改动 prompts/safety/leaderboard/ops API；未创建 commit。

## 行为摘要

- **REAL08**：`L3_MODEL_API_URL` 空/缺失立即 blocked，不 login。有 URL 时 `POST /api/prompts` 再建第二版（PUT 改内容）；不宣称 winner。404 视为 `endpoint_missing`。
- **REAL09**：只调用 `POST /api/safety/score` 一次试评；永不 POST 含 sign/approve/expert 的路径；返回恒为 `signed=False`。若 score 404 则 `expert_sign_not_automated`。
- **REAL10**：`POST /api/leaderboard/releases/publish`。404 → `endpoint_missing`；4xx → pass（诚实拒绝）；2xx → blocked `publish_not_rejected`（不把空榜发布标成合格）。
- **REAL11**：始终 blocked，文案含七天窗口未满；不改 `shadow_started_at`、不 promote。
- **REAL12**：`POST /api/ops/backup` 再 `POST /api/ops/restore-drill`（`backup_path` 查询参数）；记录 path/sha256。若 `POST /api/notifications` 200 则记 `notification_id`。

## 自审

- [x] TDD：先测后码；RED 为 `cannot import name 'real08_prompts'`。
- [x] 隔离 TestClient；`from tests import isolated_env`。
- [x] REAL08 无 L3 不 login。
- [x] REAL09 不代签；`signed` 永不为 True。
- [x] REAL10 以 4xx 为 pass；缺端点 blocked。
- [x] REAL11 不伪造七天窗口。
- [x] REAL12 备份 200，路径在隔离 `BACKUP_DIR`。
- [x] 既有 REAL01–07 用例保留。
- [x] 测试从 `backend/` 运行。
- [x] 未 git commit；未写 `backend/eval_platform.db`。

## Concerns

当前隔离库上 `POST /api/leaderboard/releases/publish` 可能对空榜返回 200（现有 leaderboard 服务未强制 4xx）。REAL10 对此记 `blocked`/`publish_not_rejected`，不把 2xx 标 pass。单测用 4xx 桩覆盖「诚实拒绝即为 pass」。
