# Task C1 报告：填充客户端与 REAL01

## 状态

**DONE** — `tests.test_real_fill` 3 项 unittest 全部通过；未 commit；未写入 `backend/eval_platform.db`。

## RED

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_real_fill -v
```

**关键输出：**

```
ImportError: Failed to import test module: test_real_fill
ModuleNotFoundError: No module named 'tools.real_fill'
FAILED (errors=1)
```

**失败原因：** 测试已引用 `tools.real_fill.client` / `scenarios`，包尚未创建（TDD 预期 RED）。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_real_fill -v
```

**结果：** `Ran 3 tests in 2.003s` — **OK**

| 用例 | 说明 |
| --- | --- |
| `test_isolated_url_is_not_business_db` | `DATABASE_URL` 经 `assert_isolated_database`，文件名不是业务库 `eval_platform.db` |
| `test_fill_client_login_admin` | `FillClient.login` 后 `GET /api/users/me` 为 200 且 username=admin |
| `test_real01_viewer_cannot_register` | `real01_accounts` 管理员登录 200；viewer `POST /api/resources/register` 为 403 |

GREEN 运行时应用层打出一次预期 `HTTPException ... status=403 | detail=需要权限: resource:create`（viewer 无 `resource:create`），不是测试失败。另有 Starlette TestClient 既有 deprecation warning。

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `tools/real_fill/__init__.py` | 新建（空包） |
| `tools/real_fill/client.py` | 新建：`FillClient.login` / `request`，登录后自动带 Bearer |
| `tools/real_fill/scenarios.py` | 新建：`real01_accounts`（仅 REAL01） |
| `backend/tests/test_real_fill.py` | 新建：隔离库 + FillClient + REAL01 |

未改动简报外代码；未创建 commit。

## 自审

- [x] TDD：先测后码；RED 为 `ModuleNotFoundError`。
- [x] `from tests import isolated_env` 后 `import os`，读 `os.environ["DATABASE_URL"]`。
- [x] `from tests.isolated_env import assert_isolated_database`。
- [x] 未调用付费模型。
- [x] 测试从 `backend/` 运行；`sys.path` 插入仓库根以导入 `tools.real_fill`。
- [x] 未 git commit；未写 `backend/eval_platform.db`。

## 关注点

1. **签名跟简报而非计划草稿：** 计划写 `real01_accounts(client)`，任务简报写 `real01_accounts(admin_client, viewer_client)`。实现为两个 `FillClient`（可包装同一 TestClient，token 分实例保存）。
2. **REAL01 会经管理员 API 创建 viewer：** 隔离库默认只有 admin；场景内 `POST /api/users` 创建 `real01-viewer-<hex>`（密码 `Test1234!`），再登录并打 register。
3. **拒绝状态实测为 403**（非 401）；断言允许 401/403。
