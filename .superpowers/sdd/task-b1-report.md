# Task B1 报告：指纹与 canonical hash

## 状态

**DONE** — `tests.test_cleanup_mock` 4 项 unittest 全部通过；未 commit；未写入 `backend/eval_platform.db`。

## RED

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock -v
```

**关键输出：**

```
ImportError: Failed to import test module: test_cleanup_mock
ModuleNotFoundError: No module named 'tools.cleanup_mock'
FAILED (errors=1)
```

**失败原因：** 测试已引用 `tools.cleanup_mock.fingerprint`，包与模块尚未创建（TDD 预期 RED）。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock -v
```

**结果：** `Ran 4 tests in 0.012s` — **OK**

| 用例 | 说明 |
| --- | --- |
| `test_resolve_rejects_business_eval_platform_name_in_tests` | `import os` 读 `DATABASE_URL`，`assert_isolated_database`；`resolve_sqlite_path` 与隔离路径一致且文件名不是业务库 `eval_platform.db` |
| `test_resolve_sqlite_path_strips_url_prefix` | SQLite URL 与裸路径均解析为同一绝对路径 |
| `test_fingerprint_changes_when_bytes_change` | `file_sha256` 匹配内容哈希；`target_fingerprint` 为 `sha256:` + 64 hex；字节变化后指纹变化；指纹 = sha256(`file_sha256` + `\|` + 绝对路径) |
| `test_manifest_hash_ignores_own_field` | `canonical_json` 稳定序列化；`manifest_hash` 忽略自身字段且不等于占位值 `"x"` |

相对计划原文多写了 `test_resolve_sqlite_path_strips_url_prefix`，并在指纹/manifest 用例中直接断言 `file_sha256` / `canonical_json`，避免接口仅被 import 未覆盖。

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `tools/cleanup_mock/__init__.py` | 新建（空包） |
| `tools/cleanup_mock/fingerprint.py` | 新建：`resolve_sqlite_path`、`file_sha256`、`target_fingerprint`、`canonical_json`、`manifest_hash` |
| `backend/tests/test_cleanup_mock.py` | 新建：FingerprintTests |

未改动简报外文件；未创建 commit。

## 自审

- [x] TDD：先测后码；RED 为 `ModuleNotFoundError`。
- [x] 不使用 `isolated_env.os`；`from tests import isolated_env` 后 `import os`，读 `os.environ["DATABASE_URL"]`。
- [x] `from tests.isolated_env import assert_isolated_database`。
- [x] `target_fingerprint` 形如 `sha256:<64hex>`，内层为 `sha256(bytes)+"|"+absolute path` 再哈希。
- [x] `manifest_hash` 忽略键 `manifest_hash`。
- [x] 测试从 `backend/` 运行；`PYTHONPATH` 通过测试内 `sys.path` 插入仓库根以导入 `tools.cleanup_mock`。
- [x] 未 git commit；未写 `backend/eval_platform.db`。

## 关注点

1. **`resolve_sqlite_path` 与计划草稿略有不同：** 未用 `split("///")`，而是 `urlparse` + `unquote`，并处理 Windows `/E:/...` 前导斜杠，与 `isolated_env.assert_isolated_database` 对齐，避免环境 URL 与解析路径不一致。
2. **相对路径依赖 cwd：** 非绝对 SQLite 路径按 `Path.cwd()` resolve；测试约定从 `backend/` 运行。
3. **`canonical_json` 只保证顶层 `sort_keys`：** 嵌套 dict 的键序由 `json.dumps(..., sort_keys=True)` 递归排序，当前用例仅覆盖一层 `actions`。
