# WP05 快照批处理与预算流水（含前端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 批处理强制 snapshot–tenant 绑定与分片边界校验；结果回写 hash 幂等；预算预占/结算与 `paused_budget`；活动快照 GC 保护；前端批次状态与任务费用视图。

**Architecture:** `batch_store` 强化绑定与 GC；`UsageReservation`/`UsageLedger` 管预占结算；`put_shard_results` 幂等+边界；任务 `token_quota` 耗尽停为 `paused_budget`；Resources/TaskDetail/Tasks UI 展示。

**Tech Stack:** FastAPI、SQLAlchemy、Vue3、unittest。

## Global Constraints

- 依赖 WP01–WP04；不信任客户端伪造 tenant/snapshot。
- 本会话不做完：完整对象存储 Artifact 适配器、workspace 微元计价、SSE 进度。

## File Map

| 路径 | 职责 |
|---|---|
| `models/usage.py`（或 resource） | UsageReservation、UsageLedger |
| `services/batch_store.py` / `budget.py` | 绑定、幂等、预占、GC |
| `api/batch.py` | 校验与 paused_budget |
| `task_runner.py` | 配额耗尽 → paused_budget |
| `frontend Resources/TaskDetail/Tasks` | 批次轮询、预算展示 |
| `tests/test_batch_budget.py` | 验收用例 |

---

### Task 1: 绑定 + 分片守卫
### Task 2: 幂等回写 + Artifact 语义（DB 行级）
### Task 3: 预算预占/结算 + paused_budget
### Task 4: GC 活动引用保护
### Task 5: 前端
### Task 6: 测试与交付
