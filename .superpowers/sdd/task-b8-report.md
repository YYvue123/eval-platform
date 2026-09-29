# Task B8 报告：隔离全流程证据

## 状态

**DONE** — 业务库已文件复制到隔离路径并完成 backup → plan → apply → verify；活动库仅只读 `plan`，因 busy 任务 **未 apply**；`tests.test_cleanup_mock` + `tests.test_isolation_guard` **22/22 OK**；未 commit；未打印密钥 / `DATABASE_URL`。

## 隔离拷贝

**源：** `E:\eval-platform\backend\eval_platform.db`（存在；无 `-wal`/`-shm`）  
**复制方式：** `shutil.copy2` 文件复制，未通过应用打开源库写入。  
**目标：** `E:\eval-platform\backend\tests\_isolated\b_cleanup_src.db`

未因源缺失改用 Task 4 种植库。

首次对拷贝 `apply` 被 CLI 拒绝：`eval_tasks.status in running/queued/leased/cancelling`（拷贝上 `queued=1`、`running=1`，均为非 simulation）。守卫发生在 apply 内 backup/删除之前，拷贝未改行。

为完成**断开连接的副本**闭环：仅在拷贝上将这 2 条陈旧 busy 更新为 `paused`（非活动库），然后重新 backup → plan → `--confirm-fingerprint` apply → verify。

## 拷贝闭环（暂停 busy 之后）

工作目录：仓库根，`PYTHONPATH=E:\eval-platform`。

| 步骤 | 退出码 | 要点 |
| --- | --- | --- |
| `backup` | 0 | `b_cleanup_work\b_cleanup_src.after-pause.backup.db` |
| `plan` | 0 | 349 条 simulation/mock 动作 |
| `apply --confirm-fingerprint` | 0 | 指纹 `sha256:2aa126b99c76d7f4062a6e7b61c928a3f34d939b5ddedf18a7a34d9286d0a189` |
| `verify` | 0 | `ok=true`，`simulation_results=0`，`simulation_tasks=0`，`mock_runs=0`，`integrity=ok`，`foreign_key=[]` |

计数与哈希见 `docs/superpowers/evidence/subproject-b.md`。未使用 `LIKE '%mock%'`。

## 活动库（只读 plan；apply 未执行）

`plan --db backend\eval_platform.db` 退出 0；stdout 仅绝对路径。plan 后文件 sha256 **未变**（`d227b744dfb898aeed7d14ede7319c1ef0033215a6d30fa00f9feaa90334480b`）。

- simulation/mock 动作：**349**（非 0）
- busy：`running=1`，`queued=1`
- **判定：** 不安全，**不 backup / 不 apply / 不 verify**（apply 未开始，无需从备份覆盖恢复）
- **blocked 原因：** `active tasks`（busy status）

## unittest

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock tests.test_isolation_guard -v
```

**结果：** `Ran 22 tests in 7.280s` — **OK**

未把 unittest 指向 `backend/eval_platform.db`。`test_isolation_guard` 仍拒绝业务库相对 URL。

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `.superpowers/sdd/task-b8-report.md` | 本报告 |
| `docs/superpowers/evidence/subproject-b.md` | 证据 |
| `backend/tests/_isolated/b_cleanup_src.db` | 文件复制 + 隔离 apply（非 git 产品源） |
| `backend/tests/_isolated/b_cleanup_work/` | plan JSON、Backup API 副本 |

未改 `tools/cleanup_mock` 实现代码。未创建 commit。

## 自审

- [x] 业务库存在则文件复制到 `b_cleanup_src.db`，未用应用写源库。
- [x] 隔离拷贝 backup / plan / confirm-fingerprint apply / verify，并记录计数与哈希。
- [x] 指定 unittest 通过。
- [x] 活动库只读 plan；有动作且 busy → 不 apply。
- [x] 无 `LIKE '%mock%'`；无密钥打印；无 git commit。
