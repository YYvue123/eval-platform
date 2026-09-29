# Task 6 实施报告：Skill 每一步经统一网关

## Status

完成。工作区已有 Task 6 主体（异步 `run_skill` + `step_invoker`、网关 `_depth`
递归、注册期 chain ACL/禁嵌套）。对照简报核验后补了一处真实 HTTP 绑定缺口：
`/v1/parse` 的业务结果是测量值列表，简报要求 `s1.output.values` 引用该列表。
未修改 D1/D2/Task 1–5 无关文件，未触碰业务库 `eval_platform.db`，未创建 commit。

## What you implemented

- `run_skill` 改为 `async`，每步 `await step_invoker`，成功用 `response_result`
  取业务结果；失败抛 `SkillStepError`（step_id、下游 code、安全 message、已完成
  steps）。
- 仅显式非 None `score` 参与平均，仅显式 `passed` 参与 all；缺失则为 `None`，
  不补 0。顶层 `result` 为最后一步结果。
- 网关 Skill 分支：`_depth >= 1` 拒绝嵌套；子步骤闭包调用 `invoke_tool`，
  actor/task_id 原样，`caller_id="skill_step"`，correlation=`{parent}:{step_id}`，
  `parent_correlation_id` 与 parent/continue trace 用父调用。
- 下游失败不写父 Skill 幂等成功；错误 code 用 `SkillStepError.code`，message
  走 Task 5 `redact_error_text`。
- 注册 Skill 时在写入 BaseResource 前校验每步 resource_id 可见，且引用类型不得
  为 skill；消息定位 `skill.chain[index]`。
- 补丁：`_step_result` 把列表型工具结果映射为 `{values: ...}`，使
  `s1.output.values` 能接到 parse 输出。

## What you tested and results

命令：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.SkillGatewayTest `
  tests.test_tool_gateway.SkillRefTest `
  tests.test_review_followup_d2.ExecutableRegisterTest -v
```

结果：`Ran 10 tests in 12.846s` **OK**。

覆盖：真实 parse→stats Skill 链、租户 ACL 注册拒绝、嵌套 Skill 注册拒绝、下游
HTTP 业务失败不写父幂等、历史嵌套 Manifest 运行时 `_depth` 拒绝、纯函数
SkillRefTest 异步 invoker、D2 可执行注册（含 skill.chain）。

## TDD Evidence

### RED

实现缺口暴露于已有集成测试（parse 列表结果无法绑定 `s1.output.values`），父
Skill `body.status=error`：

```text
FAIL: test_real_http_steps_share_parent_trace_and_history
AssertionError: 'error' != 'success'
Ran 10 tests in 13.861s
FAILED (failures=1)
```

其余 9 项已通过，失败点与绑定路径一致。

### GREEN

同一 unittest 命令：

```text
Ran 10 tests in 12.846s
OK
```

## 真实调用 ID 脱敏示例

模式（测试断言，无明文秘密）：

- 父 Skill correlation：`skill-<hex>`
- 子步骤 correlation：`skill-<hex>:s1`、`skill-<hex>:s2`（互不相同，含 step_id）
- 两条子记录 `parent_correlation_id` 均为父 correlation
- 子 `trace_id` 与父 Skill 历史记录相同
- 子 `source=skill_step`

## Files changed

- `backend/app/services/skill_runtime.py`（本会话补 `_step_result`；其余为既有 Task 6）
- `backend/app/services/tool_gateway/__init__.py`（既有：`_depth`、step 闭包）
- `backend/app/api/resources.py`（既有：注册期 chain 校验）
- `backend/tests/test_tool_gateway.py`（既有：`SkillRefTest` IsolatedAsyncio）
- `backend/tests/test_review_followup_a.py`（既有：`SkillGatewayTest`）

## Self-review findings

- Skill 步骤不再直接 `run_builtin_tool`；真实链经 `invoke_tool`。
- 注册校验在 `db.add(BaseResource)` 之前；仍走 `executable_errors`。
- `_detect_resource_cycle` 仍为空实现，向前引用已由 `resolve_value` 拒绝；未改无关死代码。
- 下游 HTTP 业务码（如 stats 的 `INVALID_INPUT`）在适配层被规范为
  `TOOL_EXEC_FAILED`；父 Skill 使用该网关稳定 code，与现有测试一致。不能改
  `http_adapter.py`（不在本任务允许文件内）。

## Issues or concerns

- `_step_result` 是 parse 列表结果与 `sN.output.values` 简报约定之间的适配；
  若未来 parse 改为对象 `{values: [...]}`，该映射仍兼容。
- 子步骤成功会在同一 Session 内 `flush` 幂等记录；父失败时子成功记录仍会随请求
  提交（简报要求父不写幂等成功，未要求回滚已成功步骤）。

## Review follow-up (Important): 步骤 HTTPException → Skill 信封

父 Skill 步骤 `invoke_tool` 在资源 404/422/409 时抛 `HTTPException`；原先网关
`except HTTPException: raise`，父调用变成业务 HTTP 错误而非 Skill 信封。

修复：`run_skill` 捕获步骤 `HTTPException`，转为 `SkillStepError`（含
`step_id`、下游 code、安全 message）。父路径走既有 `Exception` 信封（
`body.status=error`），不写父 `IdempotencyRecord`。子步骤若已写 failed 日志则
保留；404 发生在子 `try` 之前则子无日志。

### 覆盖测试

`tests.test_review_followup_a.SkillGatewayTest.test_step_http_exception_returns_skill_error_envelope`

Skill 引用已注册 Tool，下线后 invoke：HTTP 200、`body.status=error`、message
含 `offline_step`、父幂等记录数为 0。

### RED

```text
FAIL: test_step_http_exception_returns_skill_error_envelope
AssertionError: 404 != 200 : {"success":false,"code":404,"message":"..."}
Ran 1 test in 1.308s
FAILED (failures=1)
```

### GREEN 命令

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_review_followup_a.SkillGatewayTest tests.test_tool_gateway.SkillRefTest tests.test_review_followup_d2.ExecutableRegisterTest -v
```

### GREEN 输出

```text
test_downstream_failure_is_safe_logged_and_not_idempotent ... ok
test_historical_nested_manifest_is_rejected_at_runtime ... ok
test_real_http_steps_share_parent_trace_and_history ... ok
test_registration_enforces_acl_and_rejects_nested_skill ... ok
test_step_http_exception_returns_skill_error_envelope ... ok
test_forward_ref_rejected ... ok
test_non_workflow_rejected ... ok
test_workflow_input_binding ... ok
test_local_endpoint_rejected ... ok
test_plaintext_token_rejected_and_ref_kept ... ok
test_skill_requires_chain ... ok

Ran 11 tests in 17.288s
OK
```

### 本轮改动文件

- `backend/app/services/skill_runtime.py`
- `backend/tests/test_review_followup_a.py`
- `.superpowers/sdd/task-6-report.md`（本段）
