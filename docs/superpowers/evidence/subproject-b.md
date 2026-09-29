# 子项目 B 验收证据（Mock 清理）

日期：2026-09-29。工作目录：`E:\eval-platform`。未提交。未打印密码或 `DATABASE_URL`。未对活动库执行 apply。

## 环境

- HEAD：`380650893eb44871e4722100c8060def66619d56`（`Deliver frontend UX U0-U5 no-mock hardening with smoke e2e.`）
- CLI：仓库根，`PYTHONPATH=E:\eval-platform`，解释器 `backend\.venv\Scripts\python.exe -m tools.cleanup_mock`
- 隔离拷贝：`backend/tests/_isolated/b_cleanup_src.db`
- 工作产物：`backend/tests/_isolated/b_cleanup_work/`
- 活动库：`backend/eval_platform.db`（只读 `plan`）
- 约束：无 `DELETE ... LIKE '%mock%'`；unittest 不指向业务库

## 1. 文件复制（非应用写源）

| 项 | 值 |
| --- | --- |
| 源存在 | 是（无 `-wal` / `-shm`） |
| 方法 | `shutil.copy2`（字节复制 + 元数据；未用 ORM/应用打开源库写入） |
| 目标 | `E:\eval-platform\backend\tests\_isolated\b_cleanup_src.db` |
| 复制后大小 | 2899968 |
| Task 4 种植库 | 未使用（源存在，live copy **未 blocked**） |

## 2. 隔离拷贝：首次 apply 被 busy 拒绝

对刚复制的 `b_cleanup_src.db`：`backup`（`b_cleanup_src.pre-cycle.db`）与 `plan` 成功。`apply` 退出 **1**，stderr：`eval_tasks.status in running/queued/leased/cancelling`。此时拷贝只读盘点：

| 标志 | 数量 |
| --- | --- |
| `eval_results.simulation=1` | 50 |
| `eval_tasks.simulation=1` | 35 |
| `agent_runs.provider=mock` | 1 |
| busy 合计 | 2（`running=1`，`queued=1`；**均为非 simulation**） |

`plan.json`（未改 busy 前）：

- path：`E:\eval-platform\backend\tests\_isolated\b_cleanup_src.db`
- fingerprint：`sha256:173a535d32822a988e9f72b28debb34dfd8d03e29911873b98ada3690a756776`
- manifest_hash：`1b0261e69053198a68acfbcfddaf4aa7c0ccff6a1e8683dbb41e594789c9d0d8`
- actions：349（全部为 simulation=1 衍生链或 `provider=mock` 衍生链）
- counts_before：`eval_tasks=137`，`eval_results=103`，`eval_lineages=47`，`task_events=386`，`task_subtasks=67`，`report_jobs=1`，`agent_runs=1`，`agent_events=7`，`agent_messages=101`

pre-cycle backup sha256：`15f477e8110eab7885d52a1972788e3be6253b980f8fd559e406512feacdc827`

该次 apply 在 backup/删除之前失败，拷贝行未删。

## 3. 隔离拷贝闭环（仅副本清除陈旧 busy）

断开连接的副本上 busy 不表示真实调度占用。仅在拷贝执行：

`UPDATE eval_tasks SET status='paused' WHERE status IN ('running','queued','leased','cancelling')` → **2** 行。

随后：

```text
python -m tools.cleanup_mock backup --db ...\b_cleanup_src.db --out ...\b_cleanup_src.after-pause.backup.db
python -m tools.cleanup_mock plan --db ...\b_cleanup_src.db --out ...\plan-after-pause.json
python -m tools.cleanup_mock apply --db ...\b_cleanup_src.db --manifest ...\plan-after-pause.json --confirm-fingerprint sha256:2aa126b99c76d7f4062a6e7b61c928a3f34d939b5ddedf18a7a34d9286d0a189 --backup-dir ...\b_cleanup_work
python -m tools.cleanup_mock verify --db ...\b_cleanup_src.db
```

stdout 仅打印解析后的绝对路径。verify JSON：

```json
{"ok": true, "integrity": "ok", "foreign_key": [], "simulation_results": 0, "simulation_tasks": 0, "mock_runs": 0}
```

退出码 0。

### 指纹与哈希

| 对象 | sha256 或 fingerprint |
| --- | --- |
| after-pause backup 文件 | `2de73dd322a6d30a294b822154a8fe3631fdf4a8b8c19db5b2e339b1ae634330` |
| apply 前 Backup API `b_cleanup_src.pre-apply.db` | 同上（与 after-pause backup 一致） |
| plan-after-pause fingerprint | `sha256:2aa126b99c76d7f4062a6e7b61c928a3f34d939b5ddedf18a7a34d9286d0a189` |
| plan-after-pause manifest_hash | `825d87253d6b04147c4cffaf845180c06003500b81f8370847904c0b568306aa` |
| apply 后拷贝文件 | `f238abd336018ff792cf40ceb11ec8a60a18398c8465ed74f45ad6f90ba81ddb` |
| apply 后拷贝 fingerprint | `sha256:6256c032d82fb9e6dea74b97c764292f3d0bc0d8a9c2b0da67331df86b18afd7` |

plan-after-pause 仍为 **349** 条 delete；按表：`eval_results=50`，`eval_tasks=35`，`eval_lineages=35`，`task_events=180`，`task_subtasks=35`，`agent_runs=1`，`agent_events=7`，`agent_messages=6`。

### 行数（apply 前后）

| 表 | apply 前（pre-apply backup / counts_before） | apply 后 |
| --- | ---: | ---: |
| eval_tasks | 137 | 102 |
| eval_results | 103 | 53 |
| eval_lineages | 47 | 12 |
| task_events | 386 | 206 |
| task_subtasks | 67 | 32 |
| report_jobs | 1 | 1 |
| agent_runs | 1 | 0 |
| agent_events | 7 | 0 |
| agent_messages | 101 | 95 |

任务状态 apply 后：`draft=61`，`failed=3`，`paused=2`，`success=36`。simulation / mock 计数均为 0。trial / 非 simulation 行按 plan pk 保留。

## 4. 活动库（try，诚实）

只读：`python -m tools.cleanup_mock plan --db E:\eval-platform\backend\eval_platform.db --out ...\live-plan.json`

| 项 | 值 |
| --- | --- |
| plan 退出码 | 0 |
| 打印 | 仅 `E:\eval-platform\backend\eval_platform.db` |
| fingerprint | `sha256:ed3285fee44f7f1df0fd7cf0a5a99d4727ca4f627bb223d36707cad362c27991` |
| manifest_hash | `75d9d9662ae37683cf3b8555bae97a2cb89e64b42641a0bf863af326e8c090e8` |
| simulation/mock actions | **349**（非 0） |
| busy | 2（`running=1`，`queued=1`） |
| plan 前/后文件 sha256 | 均为 `d227b744dfb898aeed7d14ede7319c1ef0033215a6d30fa00f9feaa90334480b`（plan 未写库） |
| sqlite locked | 否 |

**Live apply：** **blocked** — `blocked: active tasks`。未 backup、未 apply、未 verify。apply 未开始，无需用备份覆盖恢复。

活动库盘点（只读，与 plan counts_before 一致）：`eval_tasks=137`，`eval_results=103`，`eval_lineages=47`，`task_events=386`，`task_subtasks=67`，`report_jobs=1`，`agent_runs=1`，`agent_events=7`，`agent_messages=101`；`simulation_results=50`，`simulation_tasks=35`，`mock_runs=1`。

## 5. unittest

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock tests.test_isolation_guard -v
```

`Ran 22 tests in 7.280s` — **OK**（cleanup_mock 18 + isolation_guard 4）。

`TestIsolationGuard.test_rejects_business_db_relative_url` 仍拒绝 `sqlite+aiosqlite:///../eval_platform.db`。

## 退出门禁

| 门禁 | 结果 |
| --- | --- |
| 隔离拷贝全流程 | pass（副本上暂停陈旧 busy 后 verify ok） |
| 活动库标志清零 | **blocked: active tasks**（未 apply） |
| 指定 unittest | pass |
| 无 git commit | 是 |
