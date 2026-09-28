# WP02 标准契约与统一工具网关 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 统一工具调用走 tool_gateway：规范信封 1.3（body.status/result/metadata.usage、auth.caller_id、trace 延续）、幂等、限流半开、不可变 ResourceVersion；task_runner 经网关调用裁判（含 HTTP）。

**Architecture:** `services/tool_gateway/` 为唯一执行入口；`protocol.py` 负责信封构造/校验；幂等表持久化；HTTP adapter 支持 429 退避与 trace 头；旧 `/api/resources/invoke` 转调网关。

**Tech Stack:** FastAPI、SQLAlchemy、httpx、unittest、JSON Schema（contracts/）。

## Global Constraints

- 依赖 WP01：网关调用携带 ActorContext.tenant_id，禁止信任 body.tenant_id。
- 禁止绕过对象策略；网关内校验资源可见性（builtin 除外可全租户只读）。
- Mock/占位不得标正式能力；外部 HTTP 裁判需真实产生分数。
- 交付 `docs/delivery/WP02.md`；测试隔离 DB。

## File Map

| 路径 | 职责 |
|---|---|
| `services/protocol.py` | 信封 1.3 修正、请求/响应校验 |
| `services/tool_gateway/` | invoke、idempotency、dispatch |
| `services/http_adapter.py` | 429 退避、trace 传播 |
| `models/resource.py` | ResourceVersion、IdempotencyRecord |
| `api/resources.py` | 转调网关 |
| `services/task_runner.py` | 经网关打分 |
| `tests/test_tool_gateway.py` | 契约/幂等/HTTP |

---

### Task 1: 信封与校验修正（B10）

- response：`body.status` ∈ success|error；`body.result` / `body.error`；`body.metadata.usage`（可省略非 LLM）
- `auth.caller_id` 服务端注入（gateway）
- 同链：`make_response` **延续** request `trace.trace_id`，仅新 `span_id`
- 请求校验：缺 `body.action`（或兼容旧扁平 body）/空 caller → 拒绝
- profile：`platform-v0.6.1/envelope-1.3`；ADR 记 spec_version 歧义

### Task 2: ResourceVersion + Idempotency 表

```python
class ResourceVersion(...):
    resource_id, version, manifest_json, immutable, created_at
class IdempotencyRecord(...):
    tenant_id, resource_id, version, action, correlation_id, request_hash, response_json, status
    # unique key
```

同 correlation+同 hash → 返回原结果；同 correlation+不同 hash → 409。

### Task 3: tool_gateway.invoke

```python
async def invoke_tool(*, db, actor, resource_id, body, correlation_id=None, parent_trace=None, action="execute") -> dict:
    # load resource + version freeze
    # check_gateway + object visibility (non-builtin)
    # idempotency
    # dispatch builtin/http/skill/mcp
    # record_gateway + IdempotencyRecord + ResourceCallLog
    # return standard envelope
```

### Task 4: HTTP adapter 429 退避 + trace

- 读 Retry-After；最多 N 次指数退避
- 请求头带 `traceparent` / `X-Trace-Id`
- 401/403/404 health ≠ ok（为 WP03 铺垫，本包 health_http 收紧：仅 2xx 为 ok）

### Task 5: resources.invoke + task_runner 接网关

- API 转调 `invoke_tool`
- runner 裁判：builtin 走网关；若 judge 为非 builtin HTTP 资源亦走网关并写分数

### Task 6: 测试与交付

- Schema 正反例（空 caller、错误 body）
- 幂等同/异 payload
- 子调用 trace_id 相同
- Mock HTTP 裁判任务链分数
- `docs/delivery/WP02.md` + STATUS

## Out of scope（本会话明确不做完）

- 完整 async/stream 任务子系统、Redis 令牌桶、真实 SSE 注册准入状态机（骨架/开关可留，深度属后续迭代）
- WP03 模型版本冻结全量
