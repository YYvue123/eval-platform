# Task B2 报告：SQLite Backup API

## 状态

**DONE** — `tests.test_cleanup_mock` 5 项 unittest 全部通过；未 commit；未写入 `backend/eval_platform.db`。

## RED

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock -v
```

**关键输出：**

```
ERROR: test_backup_hash_matches_restore_copy
ModuleNotFoundError: No module named 'tools.cleanup_mock.backup_sqlite'
Ran 5 tests in 0.022s
FAILED (errors=1)
```

**失败原因：** `BackupTests` 已引用 `tools.cleanup_mock.backup_sqlite`，模块尚未创建（TDD 预期 RED）。Task 1 的 4 个 FingerprintTests 仍为 ok。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock -v
```

**结果：** `Ran 5 tests in 0.101s` — **OK**

| 用例 | 说明 |
| --- | --- |
| Task 1 ×4 | `FingerprintTests` 保持通过 |
| `test_backup_hash_matches_restore_copy` | temp 库建表插入后 `consistent_backup`；目标文件存在；`info["sha256"]` 等于 `file_sha256(dest)`；返回 `path`/`source`/`size`；副本 `SELECT COUNT(*) FROM t` 为 1 |

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `tools/cleanup_mock/backup_sqlite.py` | 新建：`consistent_backup(src, dest) -> dict`（`path`, `sha256`, `source`, `size`） |
| `backend/tests/test_cleanup_mock.py` | 追加 `BackupTests`；保留 Task 1 测试 |

未改动简报外文件；未创建 commit。

## 实现要点

- 源路径经 `resolve_sqlite_path`；优先 `file:{posix}?mode=ro` URI。
- `PRAGMA wal_checkpoint(FULL)`；`OperationalError` 忽略后仍 `Connection.backup`。
- Windows：只读 URI `OperationalError` 时回退 `sqlite3.connect(str(src))` 再 checkpoint + backup。
- 目标已存在则 `unlink`；`dest.parent.mkdir(parents=True, exist_ok=True)`。

## 自审

- [x] TDD：先测后码；RED 为 `ModuleNotFoundError`。
- [x] `consistent_backup` 返回 `path, sha256, source, size`。
- [x] WAL checkpoint FULL 后 `src.backup(dest_conn)`。
- [x] Windows URI 失败回退 `connect(str(src))`。
- [x] 测试从 `backend/` 运行；未 git commit；未写 `backend/eval_platform.db`。

## 关注点

1. **只读 URI 上 checkpoint 常失败：** `mode=ro` 下 `wal_checkpoint(FULL)` 多为 `OperationalError`，被吞掉；一致性依赖 SQLite backup API 而非强制 checkpoint 成功。
2. **回退路径无单独用例：** 当前测试在本机 Windows 上 URI 成功即可通过，未强制触发 `file:?mode=ro` 失败分支。
3. **相对计划测试多断言了 `path`/`source`/`size`：** 与接口约定对齐，未改备份语义。
