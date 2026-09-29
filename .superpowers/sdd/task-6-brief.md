# Task 6：Skill 每一步经统一网关

## Context

现有 `run_skill` 是同步函数并直接 `run_builtin_tool`，绕过对象 ACL、冻结版本、
副作用策略、幂等和 ResourceCallLog。Task 5 已实现调用证据与
`parent_correlation_id`。

## Files

- Modify: `backend/app/services/skill_runtime.py`
- Modify: `backend/app/services/tool_gateway/__init__.py`
- Modify: `backend/app/api/resources.py`
- Modify: `backend/tests/test_tool_gateway.py`
- Modify: `backend/tests/test_review_followup_a.py`

不得修改其他文件。

## Interfaces

```python
async def run_skill(
    manifest: dict,
    body: dict,
    *,
    step_invoker: Callable[[str, str, dict], Awaitable[dict]],
) -> dict
```

`invoke_tool` 新增内部关键字 `_depth: int = 0`。

## Skill runtime

保留现有：
- workflow-only；
- chain/step_id/resource_id 校验；
- `$input`、`$global`、step output 引用；
- 禁止前向引用。

每步：
1. 解析 payload；
2. `await step_invoker(step_id, resource_id, payload)`；
3. 检查响应 `body.status == "success"`；
4. 失败时抛 `SkillStepError`，包含 step_id、下游 error code、安全 message、
   已完成 steps（不得泄露原始秘密）；
5. 成功用 `response_result(envelope)` 得到业务结果；
6. step entry 保存 `step_id/resource_id/result/output`。

汇总：
- 只有结果显式含非 None `score` 时才参与平均；
- 只有结果显式含 `passed` 时才参与 all；
- 没有 score → `score=None`，不得补 0；
- 没有 passed → `passed=None`；
- 顶层 `result` 等于最后一步 result；
- `metrics.steps` 与 execution_type 保留。

## Gateway recursion

Skill 分支：
- `_depth >= 1` 时拒绝，防止任何绕过注册校验的嵌套；
- 为每步构造闭包调用 `invoke_tool`：
  - actor 原样传递；
  - resource_id=步骤资源；
  - body=步骤 payload；
  - 当前 correlation id=`f"{parent_cid}:{step_id}"`；
  - `parent_correlation_id=parent_cid`；
  - parent/continue trace 使用父 trace id；
  - task_id 原样；
  - caller_id=`"skill_step"`；
  - `_depth=_depth+1`。
- 父 Skill 和子步骤日志在同一事务；
- 下游失败不能写父 Skill 幂等成功；
- 错误响应 code 优先使用 `SkillStepError.code`；
- 错误 message 继续经过 Task 5 安全消息机制。

## Registration validation

`register_resource` 对 Skill chain 每一步：
- resource_id 非空；
- 查询该资源并验证 actor 可见；
- 不可见/不存在返回 400，消息精确定位 `skill.chain[index]`；
- 被引用资源 `resource_type == "skill"` 时返回 400
  `Skill 不允许嵌套 Skill`；
- 允许已授权 builtin/tool；不执行网络探测。

此校验在写入 BaseResource 之前完成。仍保留 `protocol.executable_errors` 的结构校验。

## Tests

### 新真实集成测试

在 Task 5 的真实 stats service 上：
1. 注册 `/v1/parse` Tool；
2. 注册 `/v1/stats` Tool；
3. 注册 Skill：
   - s1 input.text ← `$input.text`
   - s2 input.values ← `s1.output.values`
   - s2 target_unit ← `$input.target_unit`
4. 调用输入 `100 cm, 2 m, 500 mm`，target_unit=m；
5. 顶层最后结果 converted `[1,2,0.5]`，mean≈3.5/3；
6. 两个工具 history 最新记录 source=skill_step；
7. 两条 `parent_correlation_id` 均为父 Skill correlation；
8. trace id 与父调用一致，子 correlation 不同且带 step_id；
9. 统计类结果无 score/passed 时父 Skill 也为 None。

### ACL/nesting/failure

- B 租户注册 Skill 引用 A 私有 Tool → 注册 400，含 `skill.chain[0]`；
- 外层 Skill 引用内层 Skill → 注册 400，含“不允许嵌套”；
- 下游 HTTP 业务失败 → 父 Skill body.status=error，code 含下游稳定 code，
  message 含 step_id；父 Skill不写幂等成功；步骤写 failed 日志；
- 即使数据库中存在历史嵌套 Skill Manifest，`_depth` 也在执行时拒绝。

### 旧纯函数测试

`test_tool_gateway.SkillRefTest` 改为 `unittest.IsolatedAsyncioTestCase`，用异步
`builtin_invoker` 包装 `run_builtin_tool` + `make_response`。这只是 unit test
double；真实执行证据由上面的 HTTP 子进程测试提供。

运行：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.SkillGatewayTest `
  tests.test_tool_gateway.SkillRefTest `
  tests.test_review_followup_d2.ExecutableRegisterTest -v
```

预期全部 PASS。

## Global constraints

- Skill 不得直接调用 builtin/runtime，所有步骤必须经统一网关。
- Agent/Skill 不得直接写调度器或评分事实。
- 测试隔离，不触碰业务库；真实集成不使用 Mock。
- 不保存或返回明文秘密。
- 当前工作区已有用户改动，不得覆盖、删除或回滚。
- 不创建 commit。

## Report

写入 `.superpowers/sdd/task-6-report.md`：RED/GREEN、真实调用 IDs/correlation/trace
的脱敏示例、测试数、文件、自审、关注点。
