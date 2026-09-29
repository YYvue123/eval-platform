# Task 5：调用证据字段、脱敏与历史 API

## Context

现有 `ResourceCallLog` 已有 `tenant_id/user_id/version/trace_id`，网关已对
success/failed/blocked 写日志，但没有脱敏输入输出证据与历史 API。Task 4 已提供
真实统计 HTTP 服务。

## Files

- Create: `backend/app/services/redaction.py`
- Modify: `backend/app/models/resource.py`
- Modify: `backend/app/database.py`
- Modify: `backend/app/services/tool_gateway/__init__.py`
- Modify: `backend/app/api/resources.py`
- Create: `backend/tests/followup_helpers.py`
- Create: `backend/tests/test_review_followup_a.py`

不得修改其他文件。

## Interfaces

```python
redact_secrets(value: Any) -> Any
evidence_digest(value: Any, limit: int = 4000) -> tuple[str, str]
GET /api/resources/calls/{rid:path}?page=1&page_size=20&status=
```

## Redaction

递归处理 dict/list。以下键（大小写不敏感）的非空值替换为：

```python
{"configured": True, "redacted": True}
```

键集合：

```python
{
    "token", "api_key", "apikey", "authorization",
    "secret", "password", "credential",
}
```

`credential_ref` 是引用名称，不是秘密，保留。

`evidence_digest`：
- 对脱敏后的完整对象使用 `json.dumps(... ensure_ascii=False, sort_keys=True, separators=(",", ":"))`；
- hash 是完整 JSON 的 sha256；
- digest 是完整 JSON 截断到 limit；
- 不修改输入对象。

`resources.py` 的 `_redact_manifest` 改为复用 `redact_secrets`，不保留第二套规则。

## ResourceCallLog additions

```python
input_digest: Text, default=""
output_digest: Text, default=""
input_hash: String(64), default=""
output_hash: String(64), default=""
source: String(32), default="gateway"
parent_correlation_id: String(128), default=""
```

`init_db()` 增加六条兼容 `ALTER TABLE`，沿用现有 `(table,column,sql)` 循环。

## Gateway evidence

`invoke_tool`：
- `started = time.perf_counter()` 必须在副作用判断之前；
- success/failed/blocked 都记录实际 server latency；
- input 对规范化后的 `params` 做 evidence digest；
- output 对 result 或 error 对象做 digest；
- source 取 `caller_id`（普通调用为 gateway）；
- parent_correlation_id 保存父调用 correlation；当前函数的
  `correlation_id` 是当前 cid，因此新增显式关键字参数
  `parent_correlation_id: str | None = None`，不得错误地把当前 cid 当父 cid；
- blocked 与 failed 不写幂等成功，现有行为保持；
- failed error code 若异常具有 `.code`，保留该 code，否则 `TOOL_EXEC_FAILED`。

使用一个局部 helper 或独立小函数消除三处分支重复；不要改变网关业务分发。

## History API

在 `/{rid:path}` 通配详情路由之前定义：

```python
@router.get("/calls/{rid:path}")
```

依赖 `require_actor("resource:view")`。流程：
1. `_visible_resource`；另一租户得到 404；
2. 查询 `ResourceCallLog.resource_id == resource.resource_id`；
3. 且 `tenant_id == str(actor.tenant_id)`，内置资源也按调用者租户隔离；
4. status 非空时过滤；
5. id desc 分页，page>=1，1<=page_size<=100；
6. 返回 `{"items": [...], "total": n}`。

每个 item 仅返回：
`id/resource_id/status/latency_ms/error_message/correlation_id/parent_correlation_id/tenant_id/user_id/version/trace_id/input_digest/output_digest/input_hash/output_hash/source/created_at`。
不返回任何原始未脱敏输入输出。

## Test helpers

`backend/tests/followup_helpers.py`：
- 文件在 `__future__` 后首先 `from tests import isolated_env`；
- `login_admin(client)`；
- `create_tenant_admin_header(client, prefix)`：从现有
  `test_review_followup_d1.ResourceAclTest` 抽取 Tenant、User、
  TenantMembership 创建和登录逻辑；
- `create_other_tenant_admin(client)` 调用上述函数；
- `tool_manifest(rid, endpoint, **overrides)`；
- `stats_service()` contextmanager：随机本机端口、真实 uvicorn 子进程、
  轮询 `/health` 最多 10 秒、finally terminate/kill；PYTHONPATH 指向仓库根；
  不传业务数据库配置。

不得修改或破坏 `test_review_followup_d1.py`。

## TDD tests

`test_review_followup_a.py` 在 `__future__` 后首先导入 `isolated_env`，覆盖：

1. 启动真实 stats service；
2. 注册 `/v1/stats` HTTP Tool；
3. 成功调用一次、空 values 业务失败一次，使用不同 correlation；
4. 历史接口 total=2，page_size=1 只返回 1；
5. status filter 正确；
6. 两条记录包含 server latency、64 字符 hash、非空 digest、version/trace/source；
7. digest 无 token/authorization 原文；
8. 失败记录 status=failed 且 error_message 非空；
9. 第二租户请求私有资源 history 得 404；
10. 内置资源由两个租户各调用一次，各自 history 只能看到自己的日志；
11. `redact_secrets` 不修改原对象、保留 credential_ref、递归脱敏；
12. hash 基于未截断完整 JSON：两个前 4000 字符相同但尾部不同的对象 hash 不同。

先观察 history route/字段不存在的 RED。

运行：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.ResourceCallEvidenceTest `
  tests.test_review_followup_a.RedactionTest `
  tests.test_review_followup_d1.ResourceAclTest -v
```

预期全部 PASS。

## Global constraints

- 所有测试先加载 `tests.isolated_env`，绝不指向业务库。
- 不保存/返回明文秘密。
- 不调用付费模型。
- 不新增权限码，复用 resource:view。
- 当前工作区已有用户改动，不得覆盖、删除或回滚。
- 不创建 commit。

## Report

写入 `.superpowers/sdd/task-5-report.md`：RED/GREEN、测试数、迁移字段、API 示例（只含脱敏值）、文件、自审、关注点。
