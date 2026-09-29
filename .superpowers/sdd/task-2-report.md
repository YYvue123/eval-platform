# Task 2 报告：修复任务后台调度导致的 SQLite 写锁

## 状态

**DONE**

事务顺序修复及空 endpoint 真实失败语义测试均已完成。最终指定的 3 项测试 **3/3 PASS**，输出中无 `database is locked`，且未恢复 Mock、假 endpoint 或网络桩。

## RED

命令：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_eval_flow.EvalFlowTest.test_end_to_end_eval `
  tests.test_eval_flow.EvalFlowTest.test_task_templates_queue_and_report `
  tests.test_eval_flow.EvalFlowTest.test_model_mapping_acl_and_scene -v
```

关键输出：

```text
OperationalError: (sqlite3.OperationalError) database is locked
[SQL: UPDATE eval_tasks SET status=?, lease_owner=?, lease_until=?, updated_at=? ...]
...
test_end_to_end_eval ... ERROR
test_task_templates_queue_and_report ... ERROR
test_model_mapping_acl_and_scene ... ERROR
Ran 3 tests in 198.708s
FAILED (errors=3)
TASK2_RED_EXIT=1
TASK2_RED_SECONDS=201.124
```

- 耗时：201.124 秒（unittest 自报 198.708 秒）。
- `database is locked`：**有**。
- 证据日志：`.superpowers/sdd/task-2-red.log`。

## 最小修改

1. `backend/app/api/tasks.py`
   - `run_task`、`retry_task_api` 均调整为：enqueue/retry → audit → commit → 登记后台调度 → return。
   - `background.add_task(...)` 之后不再使用请求会话写库。
2. `backend/app/api/agents.py`
   - `confirm_session` 使用 `should_dispatch`，先完成任务、会话、消息、经验与审计写入，commit 后才登记后台调度。
   - `act_suggestion` 先完成状态更新与 enqueue，显式 commit 后才登记后台调度。
3. `backend/tests/test_eval_flow.py`
   - 将简报指定的空 `api_url` invoke 断言改为 400，并校验 `model_api_url_required`。
   - 未恢复 Mock、stub 或硬编码成功路径。

## GREEN

命令与 RED 相同。

关键输出：

```text
test_end_to_end_eval ... FAIL
test_task_templates_queue_and_report ... FAIL
test_model_mapping_acl_and_scene ... ok
Ran 3 tests in 4.628s
FAILED (failures=2)
TASK2_GREEN_EXIT=1
TASK2_GREEN_SECONDS=6.752
```

- 耗时：6.752 秒（unittest 自报 4.628 秒）。
- `database is locked`：**无**；GREEN 日志全文检索为 0 条。
- 证据日志：`.superpowers/sdd/task-2-green.log`。
- 两个剩余失败的隔离库结果均为 `execution_status='model_failed'`、`score_status='skipped'`，错误为 `model_api_url_required:未配置 api_url，禁止 Mock 回退`。
- `test_end_to_end_eval` 和 `test_task_templates_queue_and_report` 都创建 `api_url=""` 的模型，却仍断言 trial-run 任务 `status == "success"`；这与禁止 Mock 回退冲突，不是 SQLite 写锁复发。
- 未删除隔离库：本次不是主键或重名残留冲突，无理由处理 `backend/tests/_isolated/wp00_test.db`。

## 额外验证

```text
python -m py_compile app\api\tasks.py app\api\agents.py tests\test_eval_flow.py
TASK2_PYCOMPILE_EXIT=0
```

- IDE 诊断：三个目标文件无 linter error。
- `git diff --check`：通过。
- 未创建 commit（按用户要求）。

## 文件清单

- 修改：`backend/app/api/tasks.py`
- 修改：`backend/app/api/agents.py`
- 修改：`backend/tests/test_eval_flow.py`
- 新增报告：`.superpowers/sdd/task-2-report.md`
- 测试证据：`.superpowers/sdd/task-2-red.log`、`.superpowers/sdd/task-2-green.log`

未修改、回滚、格式化或清理其他用户改动，未触碰 `backend/eval_platform.db`。

## 自审

- [x] 四个入口均在 commit 后才登记 `dispatch_queue`。
- [x] 后台任务登记后没有请求 `db` 写操作。
- [x] audit、AgentMessage、experience 和状态更新仍保留原业务语义。
- [x] 指定 invoke 负例校验 400 与 `model_api_url_required`。
- [x] 未增加 SQLite timeout，未跳过测试，未恢复 Mock。
- [x] 测试继续在 `from tests import isolated_env` 后导入应用。
- [x] 指定测试最终 3/3 PASS，且无 `database is locked`。

## 关注点

失败任务当前仍会生成明确标记 `status="failed"` 的失败报告，JSON 与 XLSX 报告接口实测均返回 200；测试按该真实语义断言，没有把失败报告当作成功评测结果。数据库模型对未评分行使用 `0.0` 默认值，结果 API 已按 `score_status` 将非 `scored` 行序列化为 `score=null`，避免把未测量误表示为零分。

## 继续执行与最终结果

上层规格明确旧空 endpoint 成功断言必须改为真实失败语义后，继续在既有三个任务文件内完成：

- `test_end_to_end_eval`：任务终态断言为 `failed`；每条结果断言 `execution_status="model_failed"`、`score_status="skipped"`、`score is None` 且错误含 `model_api_url_required`；保留 lineage、dashboard，并断言排行榜不含该任务。
- `test_task_templates_queue_and_report`：A 任务断言为 `failed`，结果行为 model failure；保留依赖排队、subtasks、events、alerts，并增加失败终态事件断言。
- 报告接口观察命令：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_eval_flow.EvalFlowTest.test_task_templates_queue_and_report -v
```

关键输出：

```text
test_task_templates_queue_and_report ... ok
Ran 1 test in 2.404s
OK
```

实测失败任务 JSON 与 XLSX 报告接口均为 200；JSON 内容 `status="failed"`，因此精确断言失败报告而非不存在或成功报告。

首次三项复跑揭示真实字段差异：

```text
AssertionError: 0.0 is not None
Ran 3 tests in 4.679s
FAILED (failures=2)
TASK2_FINAL_SECONDS=6.662
```

原因是数据库 `score` 默认值将未评分行表现为 `0.0`。最小修正为结果 API 仅对 `score_status="scored"` 返回数值，其他状态返回 `null`。

最终命令：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_eval_flow.EvalFlowTest.test_end_to_end_eval `
  tests.test_eval_flow.EvalFlowTest.test_task_templates_queue_and_report `
  tests.test_eval_flow.EvalFlowTest.test_model_mapping_acl_and_scene -v
```

最终关键输出：

```text
test_end_to_end_eval ... ok
test_task_templates_queue_and_report ... ok
test_model_mapping_acl_and_scene ... ok
Ran 3 tests in 4.891s
OK
TASK2_FINAL_EXIT=0
TASK2_FINAL_SECONDS=6.992
```

- 最终耗时：6.992 秒（unittest 自报 4.891 秒）。
- 最终 `database is locked`：**无**，日志全文检索 0 条。
- 最终证据日志：`.superpowers/sdd/task-2-green-final.log`。
- commit：无（按用户要求）。

## Important 审查修复：手动报告渲染

审查确认 `/api/tasks/{task_id}/report/render` 原先直接写入数据库默认 `score=0.0`，且逐项缺少 `score_status`、`execution_status`，会把未评分项误表示为零分。

### RED

先在 `test_task_templates_queue_and_report` 中实际 POST `/api/tasks/{a_id}/report/render`，再读取 JSON 报告并断言失败项的分数和状态。

命令：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_eval_flow.EvalFlowTest.test_task_templates_queue_and_report -v
```

关键输出：

```text
FAIL: test_task_templates_queue_and_report
File "backend/tests/test_eval_flow.py", line 443
  self.assertIsNone(rendered_items[0]["score"])
AssertionError: 0.0 is not None
Ran 1 test in 2.183s
FAILED (failures=1)
TASK2_REVIEW_RED_EXIT=1
TASK2_REVIEW_RED_SECONDS=4.239
```

失败原因符合预期：手动渲染报告仍把 `model_failed/skipped` 行写为 `score=0.0`。

### 最小修复

`render_task_report` 的逐项报告数据与 `task_results` 对齐：

- 仅 `score_status == "scored"` 时输出数值，否则输出 `score=null`；
- 明确输出 `score_status`；
- 明确输出 `execution_status`。

测试同时校验渲染任务 `status="ready"`，以及随后 JSON 报告中的失败项：

```text
score = null
score_status = skipped
execution_status = model_failed
```

### GREEN

命令：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_eval_flow.EvalFlowTest.test_end_to_end_eval `
  tests.test_eval_flow.EvalFlowTest.test_task_templates_queue_and_report `
  tests.test_eval_flow.EvalFlowTest.test_model_mapping_acl_and_scene -v
```

关键输出：

```text
test_end_to_end_eval ... ok
test_task_templates_queue_and_report ... ok
test_model_mapping_acl_and_scene ... ok
Ran 3 tests in 4.823s
OK
TASK2_REVIEW_GREEN_EXIT=0
TASK2_REVIEW_GREEN_SECONDS=6.849
```

- GREEN：3/3 PASS。
- `database is locked`：**无**，日志全文检索 0 条。
- RED 证据：`.superpowers/sdd/task-2-review-red.log`。
- GREEN 证据：`.superpowers/sdd/task-2-review-green.log`。
- 未增加 timeout、未恢复 Mock、未创建 commit。
