# Task C6 报告：CLI 与证据

## 状态

**DONE** — `tests.test_real_fill` + `tests.test_isolation_guard` 共 28 项 unittest 全部通过；未 commit；未写入 `backend/eval_platform.db`；未打印 API Key / 模型 URL。证据 `docs/superpowers/evidence/subproject-c.md` 按隔离 JSON 诚实记录 REAL01–12；live REAL01/02/04/05 因 8001 未监听标 blocked。

## RED

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_real_fill.RealFillTests.test_cli_missing_or_mismatch_fingerprint_exits_1_no_http tests.test_real_fill.RealFillTests.test_cli_empty_only_dry_run_lists_scenarios tests.test_real_fill.RealFillTests.test_cli_matching_fingerprint_uses_httpx_not_testclient tests.test_real_fill.RealFillTests.test_isolated_evidence_dump_json -v
```

**关键输出：**

```
ModuleNotFoundError: No module named 'tools.real_fill.cli'
FAILED (errors=4)
```

**失败原因：** 测试已引用 `tools.real_fill.cli.main` / `dump_isolated_evidence`，模块尚未创建（TDD 预期 RED）。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_real_fill tests.test_isolation_guard -v
```

**结果：** `Ran 28 tests in 16.182s` — **OK**

| 用例 | 说明 |
| --- | --- |
| 既有 REAL01–12 场景与负例 | 全部保留并通过 |
| `test_cli_missing_or_mismatch_fingerprint_exits_1_no_http` | 缺指纹或错指纹退出 1；httpx 未被调用 |
| `test_cli_empty_only_dry_run_lists_scenarios` | `--only` 空列出 REAL01–12，不 POST |
| `test_cli_matching_fingerprint_uses_httpx_not_testclient` | 指纹匹配且 `--only REAL09` 走 `httpx.Client` |
| `test_cli_dry_run_from_repo_root_subprocess` | 仓库根 `python -m tools.real_fill` dry-run 退出 0 |
| `test_isolated_evidence_dump_json` | TestClient 跑 12 场景写隔离 JSON；无 L3 则 03/06/07/08 blocked |
| `tests.test_isolation_guard` | 4 项隔离路径守卫 |

GREEN 运行时仍有预期 403 register、空 url invoke 400，以及 Starlette TestClient deprecation warning。

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `tools/real_fill/cli.py` | 新建：指纹闸门、dry-run、httpx `--only`、隔离 dump |
| `tools/real_fill/__main__.py` | 新建：`python -m tools.real_fill` |
| `backend/tests/test_real_fill.py` | CLI / dump / 仓库根 subprocess 用例 |
| `docs/superpowers/evidence/subproject-c.md` | REAL01–12 诚实结果 |
| `.superpowers/sdd/progress.md` | Task 6 complete |

未创建 commit。

## 行为摘要

- 缺 `--confirm-fingerprint` 或与 `target_fingerprint(db)` 不符：退出 1，不向 `--base-url` 发写请求。
- `--only` 空：dry-run 列出 12 场景；可选 `GET /api/live`；无场景 POST。
- `--only` 非空：`httpx.Client(base_url=…)`，不用 TestClient。
- 隔离证据：`dump_isolated_evidence` + JSON。
- live：8001 不可达；拒绝用 8000 填业务库。

## 自审

- [x] TDD：先测后码；RED 为缺少 `tools.real_fill.cli`。
- [x] 隔离 unittest；`from tests import isolated_env`。
- [x] 指纹失败不写远程。
- [x] 场景 HTTP 用 httpx。
- [x] 证据 REAL01–12 诚实；live 不安全不标 pass。
- [x] REAL03/06/07/08 无 L3 → blocked；不打印 URL。
- [x] `unittest tests.test_real_fill tests.test_isolation_guard -v` OK。
- [x] 未 git commit；未写 `eval_platform.db`。

## Concerns

- 隔离库上 `POST /api/leaderboard/releases/publish` 仍可能对空榜返回 200；REAL10 记 `blocked`/`publish_not_rejected:200`。
- 未启动 8001，活动库 REAL01/02/04/05 只能 blocked。
