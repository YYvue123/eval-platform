# Task B5 报告：verify

## 状态

**DONE** — `tests.test_cleanup_mock` 14 项 unittest 全部通过；未 commit；未写入 `backend/eval_platform.db`。

## RED

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock -v
```

**关键输出：**

```
ERROR: test_after_apply_plan_ok
ERROR: test_dirty_fixture_not_ok
ModuleNotFoundError: No module named 'tools.cleanup_mock.verify'
Ran 14 tests in 0.948s
FAILED (errors=2)
```

**失败原因：** `VerifyTests` 已引用 `tools.cleanup_mock.verify.verify_clean`，模块尚未创建（TDD 预期 RED）。Task 1–4 的 12 项仍为 ok。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock -v
```

**结果：** `Ran 14 tests in 1.181s` — **OK**

| 用例 | 说明 |
| --- | --- |
| Task 1 ×4、Task 2 ×1、Task 3 ×2、Task 4 ×5 | 保持通过 |
| `test_dirty_fixture_not_ok` | tempfile 种植 simulation 任务/结果与 `provider=mock` run；`verify_clean` 的 `ok` 为 False；`simulation_results`/`simulation_tasks`/`mock_runs` 均 > 0；含 `integrity`/`foreign_key` |
| `test_after_apply_plan_ok` | 清理前 `ok` False；`apply_plan` 后 `ok` True；三项计数为 0；`integrity=="ok"`；`foreign_key==[]` |

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `tools/cleanup_mock/verify.py` | 新建：`verify_clean(db_path) -> dict` |
| `backend/tests/test_cleanup_mock.py` | 追加 `VerifyTests`；保留 Task 1–4 测试 |

未改动简报外文件；未创建 commit。未写入 `backend/eval_platform.db`（种植库均为 tempfile）。

## 实现要点

- `PRAGMA integrity_check`：取首行文本；干净库为 `"ok"`。
- `PRAGMA foreign_key_check`：行列表；空列表视为通过。
- 计数仅在表与列存在时查询：`eval_results.simulation=1`、`eval_tasks.simulation=1`、`agent_runs.provider='mock'`；缺表/缺列计 0。
- `ok` 为 integrity 为 ok、外键检查为空、且三项计数均为 0。
- 只读查询，不写库；不使用 `LIKE '%mock%'`。

## 自审

- [x] TDD：先测后码；RED 为 `ModuleNotFoundError`。
- [x] 脏 fixture `ok` False；apply 后 `ok` True。
- [x] 返回键含 `ok, integrity, foreign_key, simulation_results, simulation_tasks, mock_runs`。
- [x] 测试从 `backend/` 运行；未 git commit；未写 `backend/eval_platform.db`。

## 关注点

1. **缺列不计失败：** 无 `simulation`/`provider` 时计数为 0，只要 integrity/FK 通过即 `ok` True（与 inventory 跳过缺列一致）。
2. **未声明 FK 时 `foreign_key_check` 为空：** 种植表无 FOREIGN KEY 约束，脏库仍可能 FK 为空，靠 simulation/mock 计数使 `ok` False。
3. **`foreign_key` 为 list-of-list：** 与 sqlite 行元组对应，干净库为 `[]`。
