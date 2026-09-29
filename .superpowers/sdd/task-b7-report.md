# Task B7 报告：CLI

## 状态

**DONE** — `tests.test_cleanup_mock` 18 项 unittest 全部通过；未 commit；未写入 `backend/eval_platform.db`。

## RED

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock.CliTests -v
```

**关键输出：**

```
FAIL: test_plan_cli_does_not_write
AssertionError: 1 != 0 : ... python.exe: No module named tools.cleanup_mock.__main__; 'tools.cleanup_mock' is a package and cannot be directly executed
Ran 3 tests in 0.609s
FAILED (failures=3)
```

**失败原因：** `CliTests` 已通过 `python -m tools.cleanup_mock` 调子命令，包内尚无 `__main__.py` / `cli.py`（TDD 预期 RED）。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock -v
```

**结果：** `Ran 18 tests in 7.002s` — **OK**

| 用例 | 说明 |
| --- | --- |
| Task 1–6 ×15 | 保持通过 |
| `test_plan_cli_does_not_write` | subprocess + ApplyTests 种植 schema；`plan --db --out` 后 mtime_ns / 文件 hash / 各表行数不变；stdout 含解析后绝对路径；stdout/stderr 不含 `DATABASE_URL` |
| `test_apply_cli_without_confirm_exits_nonzero` | 无 `--confirm-fingerprint` 时退出码非 0；任务行仍为 2 |
| `test_apply_verify_backup_cli` | `backup` 写出可查询副本；`apply` 带指纹成功；`verify` 末行 JSON `ok` True |

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `tools/cleanup_mock/cli.py` | 新建：argparse 子命令 `plan` / `apply` / `verify` / `backup` |
| `tools/cleanup_mock/__main__.py` | 新建：`python -m tools.cleanup_mock` 入口 |
| `backend/tests/test_cleanup_mock.py` | 追加 `CliTests`（subprocess，cwd 仓库根，`PYTHONPATH=ROOT`）；保留既有测试 |

未创建 commit。种植库均为 tempfile；`DATABASE_URL` 由 `isolated_env` 指向 `backend/tests/_isolated/`。

## 实现要点

- 必须在仓库根运行（或设 `PYTHONPATH` 为仓库根）。
- 解析 `--db` 后只打印 `Path.resolve()` 绝对路径，不打印 `DATABASE_URL`。
- `apply` 将 `--confirm-fingerprint` 设为必填；缺参数由 argparse 非零退出。
- `apply` 读 `--manifest` JSON，调用 `apply_plan`；`ValueError` 写 stderr 并返回 1。
- `verify` 打印路径后打印 JSON 报告；`ok` 为 False 时退出码 1。
- `backup` 调用 `consistent_backup` 到 `--out`。

## 自审

- [x] TDD：先测后码；RED 为缺少 `__main__`。
- [x] 四条子命令按简报接口实现。
- [x] `plan` 不改库；`apply` 无 confirm 非零。
- [x] 测试从 `backend/` 运行；未 git commit；未写业务库。

## 关注点

1. **Backup API 字节不一定等于源文件：** 测试改为校验备份可打开且行数一致，不比较源/备份 sha256。
2. **`verify` 脏库退出 1：** 简报未强制；实现按报告 `ok` 映射退出码，干净库仍为 0。
3. **缺 `--confirm-fingerprint` 退出码为 2：** argparse 用法错误，测试只断言非 0。
