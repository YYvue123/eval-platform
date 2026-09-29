# Task B6 报告：停止 seed 回灌

## 状态

**DONE** — `tests.test_cleanup_mock tests.test_eval_flow tests.test_isolation_guard` 共 31 项 unittest 全部通过；未 commit；未写入 `backend/eval_platform.db`。

## RED

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock.SeedTests -v
```

**关键输出：**

```
FAIL: test_seed_db_does_not_insert_pack_datasets
AssertionError: 33 != 0
Ran 1 test in 4.660s
FAILED (failures=1)
```

**失败原因：** 隔离库 `drop_all` 后 `init_db`+`seed_db` 仍调用 `seed_eval_packs`，插入 33 条 `pack:*` 数据集（TDD 预期 RED）。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock tests.test_eval_flow tests.test_isolation_guard -v
```

**结果：** `Ran 31 tests in 12.806s` — **OK**

| 用例 | 说明 |
| --- | --- |
| Task 1–5 ×14 | 保持通过 |
| `SeedTests.test_seed_db_does_not_insert_pack_datasets` | 隔离 URL 上 drop schema 后 `init_db`+`seed_db`：`Dataset.name LIKE 'pack:%'` 计数为 0；两条示例知识标题不存在；`ref_type=template` 条目 > 0 |
| `tests.test_eval_flow` ×12 | `test_task_templates_queue_and_report` 改为显式 `await seed_eval_packs(db)` 后再断言 `pack_dataset_id` |
| `tests.test_isolation_guard` ×4 | 保持通过 |

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `backend/app/database.py` | `seed_db` 不再调用 `seed_eval_packs`；`seed_knowledge` 不再插入「任务失败不自动恢复」「内置裁判画像」 |
| `backend/tests/test_cleanup_mock.py` | 追加 `SeedTests` |
| `backend/tests/test_eval_flow.py` | 依赖 packs 的用例显式调用 `seed_eval_packs` |

`backend/app/services/eval_packs.py` 的 `seed_eval_packs` **保留**，供显式调用。未创建 commit。未写入 `backend/eval_platform.db`（`DATABASE_URL` 由 `isolated_env` 指向 `backend/tests/_isolated/`）。

## 实现要点

- `seed_db` 在 `sync_benchmark_suites` 之后直接进入 `seed_alert_policies`。
- `seed_knowledge` 仅按 `TaskTemplate` 写 `ref_type="template"` 条目。
- 行为测试必须 `drop_all` 再 seed：共享隔离库可能残留旧 pack 行，仅断言源码不够。

## 自审

- [x] TDD：先测后码；RED 为 `33 != 0`。
- [x] `seed_db` 不回灌 pack；`seed_eval_packs` 函数仍在。
- [x] 示例知识两条不再插入；模板 ref 保留。
- [x] 测试从 `backend/` 运行；未 git commit；未写业务库。

## 关注点

1. **隔离库被 SeedTests `drop_all`：** 同进程后续用例依赖 lifespan `init_db`+`seed_db` 重建；指定套件顺序下 eval_flow 仍绿。
2. **活动业务库已有 pack 行不会被本改动删除：** 只停止重启回灌；存量清理走后续 CLI apply。
3. **Starlette TestClient 弃用警告：** 与既有 eval_flow 相同，非本任务引入。
