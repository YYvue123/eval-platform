# Task 1：强制测试隔离

## Files

- Modify: `backend/tests/isolated_env.py`
- Create: `backend/tests/test_isolation_guard.py`

## Required interface

`assert_isolated_database(url: str) -> Path`

SQLite 文件必须位于 `backend/tests/_isolated/`；非 SQLite URL 和业务库路径均拒绝。

## TDD steps

1. 先创建 `backend/tests/test_isolation_guard.py`，覆盖：
   - 接受 `backend/tests/_isolated/guard.db`；
   - 拒绝 `sqlite+aiosqlite:///../eval_platform.db`；
   - 拒绝 `postgresql+asyncpg://localhost/eval`。
2. 运行：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_isolation_guard -v
```

确认因无法导入 `assert_isolated_database` 而失败。

3. 修改 `backend/tests/isolated_env.py`：
   - `_ROOT = (Path(__file__).resolve().parent / "_isolated").resolve()`；
   - 创建 uploads/logs/backups 子目录；
   - 使用 `urlparse` + `unquote` 解析 `sqlite+aiosqlite:///` URL；
   - Windows 绝对路径 `/E:/...` 去掉首个 `/`；
   - 相对路径按当前工作目录 resolve；
   - 使用 `path.relative_to(_ROOT)` 强制路径位于隔离根目录；
   - 非 `sqlite+aiosqlite:///` 抛 `RuntimeError`；
   - 现有 `DATABASE_URL` 通过断言才保留，否则显式覆盖为 `_isolated/wp00_test.db`；
   - 最终再次断言；
   - `UPLOAD_DIR`、`LOG_DIR`、`BACKUP_DIR`、`LOG_LEVEL` 均显式赋值，不用 `setdefault`。
4. 重新运行测试，预期 3 项 PASS。
5. 再运行：

```powershell
.venv\Scripts\python.exe -c "import os; os.environ['DATABASE_URL']='sqlite+aiosqlite:///E:/eval-platform/backend/eval_platform.db'; from tests import isolated_env; print(os.environ['DATABASE_URL'])"
```

预期输出路径位于 `backend/tests/_isolated/`。

## Global constraints

- 测试绝不指向 `backend/eval_platform.db`。
- 后端解释器使用 `.venv\Scripts\python.exe`，测试框架为 unittest。
- 只改本任务文件，不做相邻重构。
- 当前工作区已有用户改动；不得覆盖、删除或回滚。
- 用户要求不提交 commit。完成后保留未提交改动。

## Report

将完整报告写到 `.superpowers/sdd/task-1-report.md`，必须包含：
- RED 命令、关键失败输出和失败原因；
- GREEN 命令、通过数量；
- 修改文件；
- 自审结果与关注点。
