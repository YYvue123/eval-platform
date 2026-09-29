# Task 2：修复任务后台调度导致的 SQLite 写锁

## Files

- Modify: `backend/app/api/tasks.py`
- Modify: `backend/app/api/agents.py`
- Modify: `backend/tests/test_eval_flow.py`

## Confirmed root cause

`docs/superpowers/eval_flow_baseline.log` 已复现两条 `database is locked`。
FastAPI 0.141 / Starlette 1.6 在发送响应时执行 `BackgroundTasks`，此时
`get_db()` 依赖尚未最终提交。当前端点先登记 `dispatch_queue`，随后请求会话
继续写审计、AgentMessage 或 experience；后台的新会话进入
`recover_expired_leases`，与请求会话争夺 SQLite 写锁并等待 60 秒超时。

## Required changes

### 1. Tasks API

`run_task` 与 `retry_task_api` 都必须采用：

1. enqueue/retry；
2. `log_audit`；
3. `await db.commit()`；
4. `background.add_task(dispatch_queue, t.id)`；
5. return。

登记后台任务之后不得再通过请求 `db` 写入。

### 2. Agents API

`confirm_plan`：

- 使用 `should_dispatch = False`；
- execute 时 enqueue、设置 `s.status = "running"`、标记 should_dispatch；
- 非 execute 时 `s.status = "done"`；
- 然后完成 AgentMessage、archive_experience、log_audit；
- `await db.commit()`；
- 仅 commit 后登记 `background.add_task(dispatch_queue, t.id)`。

`act_suggestion`：

- 状态更新与 enqueue 都先写入；
- commit；
- 最后登记 background task；
- 后台任务登记后不得再写 db。

### 3. 过时 Mock 断言

`test_model_mapping_acl_and_scene` 创建的模型 `api_url=""`。其 invoke 不能再期望
200 Mock 成功，必须断言：

```python
inv = client.post(f"/api/models/{mid}/invoke", json={"prompt": "hi"}, headers=h)
self.assertEqual(inv.status_code, 400, inv.text)
self.assertIn("model_api_url_required", inv.text)
```

保留该负例，不恢复 Mock 回退。

## TDD / verification

先运行以下命令确认基线失败（若 Task 1 的隔离守卫导致测试使用新的空库，这仍是正确
隔离行为；允许测试初始化该隔离库）：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_eval_flow.EvalFlowTest.test_end_to_end_eval `
  tests.test_eval_flow.EvalFlowTest.test_task_templates_queue_and_report `
  tests.test_eval_flow.EvalFlowTest.test_model_mapping_acl_and_scene -v
```

完成修改后运行同一命令，预期 3/3 PASS，输出无 `database is locked`。

如果单个测试因历史隔离库残留发生主键/重名冲突，只能删除本任务使用的
`backend/tests/_isolated/wp00_test.db` 后重跑；不得触碰 `backend/eval_platform.db`。

## Global constraints

- 测试文件必须在 `__future__` 后首先 `from tests import isolated_env`。
- 测试绝不指向 `backend/eval_platform.db`。
- 不恢复 Mock、stub 或硬编码成功路径。
- 只修改本任务列出的三个文件，不做相邻重构。
- 当前工作区已有用户改动，不得覆盖、删除或回滚。
- 用户要求不创建 commit。

## Report

写入 `.superpowers/sdd/task-2-report.md`：
- RED/GREEN 命令、关键输出、耗时；
- 明确输出中是否仍有 `database is locked`；
- 修改文件、自审与关注点。
