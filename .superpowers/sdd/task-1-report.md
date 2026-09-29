# Task 1 报告：强制测试隔离

## 状态

**DONE** — 3 项 unittest 通过；业务库 URL 导入时被重写至 `backend/tests/_isolated/`。

## RED

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_isolation_guard -v
```

**关键输出：**

```
ImportError: cannot import name 'assert_isolated_database' from 'tests.isolated_env'
...
FAILED (errors=1)
```

**失败原因：** `test_isolation_guard.py` 已创建并引用 `assert_isolated_database`，`isolated_env.py` 尚未实现该函数（TDD 预期 RED）。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_isolation_guard -v
```

**结果：** `Ran 3 tests in 0.004s` — **OK**

| 用例 | 说明 |
| --- | --- |
| `test_accepts_isolated_sqlite_path` | 接受 `_isolated/guard.db` |
| `test_rejects_business_db_relative_url` | 拒绝 `sqlite+aiosqlite:///../eval_platform.db` |
| `test_rejects_non_sqlite_url` | 拒绝 `postgresql+asyncpg://localhost/eval` |

**简报附加验证：**

```powershell
.venv\Scripts\python.exe -c "import os; os.environ['DATABASE_URL']='sqlite+aiosqlite:///E:/eval-platform/backend/eval_platform.db'; from tests import isolated_env; print(os.environ['DATABASE_URL'])"
```

**输出：**

```
sqlite+aiosqlite:///E:/eval-platform/backend/tests/_isolated/wp00_test.db
```

业务库路径未保留，已覆盖为隔离目录下的 `wp00_test.db`。

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `backend/tests/isolated_env.py` | 修改：`_ROOT` resolve、`assert_isolated_database`、URL 解析与 `relative_to(_ROOT)`、模块加载时 DATABASE_URL 断言/覆盖、显式设置 UPLOAD/LOG/BACKUP/LOG_LEVEL |
| `backend/tests/test_isolation_guard.py` | 新建：3 个 guard 用例 |

未改动简报外文件；未创建 commit（按用户要求）。

## 自审

- [x] 仅改简报列出的两个文件。
- [x] `_ROOT = (Path(__file__).resolve().parent / "_isolated").resolve()`。
- [x] uploads / logs / backups 子目录在启动时创建。
- [x] `urlparse` + `unquote`；Windows `/E:/...` 去首 `/`；相对路径按 `Path.cwd()` resolve。
- [x] 非 `sqlite+aiosqlite:///` → `RuntimeError`；路径不在 `_ROOT` 下 → `RuntimeError`。
- [x] 环境变量不再使用 `setdefault`，均为显式赋值。
- [x] 导入时：现有 `DATABASE_URL` 仅断言通过才保留，否则 `_default_db_url`；最后再断言一次。

## 关注点

1. **导入副作用：** 任何 `from tests import isolated_env` 或 `from tests.isolated_env import ...` 都会立即改写 `os.environ`；与现有测试套件「先 import isolated_env 再 import app」的约定一致，但新测试若在未设 env 时期望保留业务 URL 会失败——这正是本任务目标。
2. **相对 SQLite URL：** `../eval_platform.db` 经 cwd resolve 后若落在 `_ROOT` 外会被拒绝；若某 CI 的 cwd 异常，错误信息中的绝对路径有助于排查。
3. **重复导入：** Python 模块缓存意味着同一进程内第二次 `import isolated_env` 不会重跑模块级逻辑；简报验证命令在 import 前设置 env，行为正确。
4. **后续任务：** 其他测试文件是否一律在文件头 import `isolated_env` 未在本 Task 范围；全量回归仍依赖后续任务与现有习惯。

## Fix Review Findings

**RED（新增相对路径用例，未修解析前）：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_isolation_guard -v
```

```
RuntimeError: Database path must be under E:\eval-platform\backend\tests\_isolated; got E:\tests\_isolated\relative.db from 'sqlite+aiosqlite:///tests/_isolated/relative.db'
FAILED (errors=1)
```

原因：`urlparse` 得到带前导 `/` 的路径时，`Path(...).is_absolute()` 在 Windows 上为真，误按盘根解析而非 `Path.cwd()`。

**修复：** `isolated_env.py` 仅当 `/X:/` 盘符形式视为绝对路径；其余去掉前导 `/` 后 `(Path.cwd() / raw).resolve()`。测试文件改为 `from tests import isolated_env` 后从模块取符号。

**GREEN：**

```powershell
.venv\Scripts\python.exe -m unittest tests.test_isolation_guard -v
```

```
test_accepts_isolated_sqlite_path ... ok
test_accepts_three_slash_relative_url_under_isolated_root ... ok
test_rejects_business_db_relative_url ... ok
test_rejects_non_sqlite_url ... ok
Ran 4 tests in 0.004s
OK
```

**结果：** 4/4 PASS。未提交 commit（按用户要求）。

## Fix Review Findings（import 顺序）

**变更：** `test_isolation_guard.py` 在 `from __future__ import annotations` 之后立即 `from tests import isolated_env`，位于 `unittest`、`pathlib` 等所有其他 imports 之前。

**验证：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_isolation_guard -v
```

```
test_accepts_isolated_sqlite_path ... ok
test_accepts_three_slash_relative_url_under_isolated_root ... ok
test_rejects_business_db_relative_url ... ok
test_rejects_non_sqlite_url ... ok
Ran 4 tests in 0.003s
OK
```

**结果：** 4/4 PASS。未提交 commit（按用户要求）。
