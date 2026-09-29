# Task B3 报告：plan 清单（不写库）

## 状态

**DONE** — `tests.test_cleanup_mock` 7 项 unittest 全部通过；未 commit；未写入 `backend/eval_platform.db`。

## RED

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock -v
```

**关键输出：**

```
ERROR: test_plan_does_not_write
ERROR: test_plan_notes_missing_tables_and_columns
ModuleNotFoundError: No module named 'tools.cleanup_mock.inventory'
Ran 7 tests in 0.072s
FAILED (errors=2)
```

**失败原因：** `PlanTests` 已引用 `tools.cleanup_mock.inventory.build_plan`，模块尚未创建（TDD 预期 RED）。Task 1/2 的 5 项仍为 ok。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock -v
```

**结果：** `Ran 7 tests in 0.276s` — **OK**

| 用例 | 说明 |
| --- | --- |
| Task 1 ×4、Task 2 ×1 | 保持通过 |
| `test_plan_does_not_write` | tempfile 种植 simulation 任务/结果、lineage、mock run/event 与 `trial_run=1 AND simulation=0` 任务；`build_plan` 后各表行数不变；actions 含 `eval_results`/`eval_tasks`/`eval_lineages`/`agent_runs`/`agent_events`；任务 pk 含 1 不含 2；结果 pk 仅 10；`action=delete`；`target.absolute_path`/`fingerprint` 与文件一致；`counts_before` 正确；`manifest_hash` 可重算 |
| `test_plan_notes_missing_tables_and_columns` | 仅有无 `simulation` 列的 `eval_tasks` 时 `actions=[]`，行数不变，`notes` 记录缺列 |

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `tools/cleanup_mock/inventory.py` | 新建：`build_plan(db_path) -> dict` |
| `backend/tests/test_cleanup_mock.py` | 追加 `PlanTests`；保留 Task 1/2 测试 |

未改动简报外文件；未创建 commit。

## 实现要点

- 只读打开：优先 `file:{posix}?mode=ro`；`OperationalError` 时回退 `sqlite3.connect(str(path))`，仅 SELECT。
- 删除候选：`eval_results.simulation=1`；`eval_tasks.simulation=1` 及 `eval_lineages`/`task_events`/`task_subtasks`/`report_jobs`（按 `task_id`）；`agent_runs.provider='mock'` 及 `agent_events`（`run_id`）、`agent_messages`（`session_id`）。
- 缺表写入 `notes`（`skip missing table …`）；缺列跳过查询并记 note；不使用 `LIKE '%mock%'`。
- 返回 `target.absolute_path`、`target.fingerprint`、`counts_before`、`actions[{table,pk,action,reason}]`、`notes`，末尾 `manifest_hash`。

## 自审

- [x] TDD：先测后码；RED 为 `ModuleNotFoundError`。
- [x] plan 不改变行数。
- [x] 保留 `trial_run=1 AND simulation=0`。
- [x] 缺表/缺列记 `notes`。
- [x] 测试从 `backend/` 运行；未 git commit；未写 `backend/eval_platform.db`。

## 关注点

1. **缺表也会进 notes：** 最小种植库没有 `task_events` 等表时，`test_plan_does_not_write` 不断言 `notes` 为空；apply 任务可忽略这些 skip notes。
2. **simulation 结果与任务独立扫描：** 只删 `simulation=1` 的结果行，不会因为任务是 simulation 就删掉该任务下 `simulation=0` 的结果（本轮种植数据无此交叉行）。
3. **agent_messages 按 session_id：** 模型无 `run_id`；mock run 的 `session_id` 命中才入清单。
