# WP04 独立 worker 与可靠任务状态机（含前端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 任务领取带 lease/fencing、逐样本提交使进度对外可见、取消/重试可靠；前端任务列表与详情可实时看进度并操作取消/重试；顺带补齐 WP03 门禁相关 UI 提示。

**Architecture:** `TaskService` 统一入队；`claim_task` 短事务写 `lease_owner`/`lease_until`/`fencing_token`；runner 每样本 `commit` 并用 fencing 校验回写；API 进程内 worker 循环与可选 `python -m app.worker` 共用 claim；前端轮询 + 取消/重试按钮。

**Tech Stack:** FastAPI、SQLAlchemy、Vue3、unittest。

## Global Constraints

- 依赖 WP01–WP03；正式任务门禁与冻结配置不回退。
- SQLite 下用条件 UPDATE 模拟互斥（无 SKIP LOCKED）；接口语义与 PG 一致。
- 本会话不做完：多租户公平配额、完整 outbox/SSE、分布式多机编排 UI。

## File Map

| 路径 | 职责 |
|---|---|
| `models/eval_task.py` | lease/fencing/cancel_requested/attempt 字段 |
| `services/task_service.py` | create/enqueue/cancel/retry/claim/heartbeat |
| `services/task_queue.py` / `worker.py` | claim 后执行、回收过期 lease |
| `services/task_runner.py` | 逐样本 commit + fencing 校验 + 取消探测 |
| `api/tasks.py` | retry、进度字段暴露 |
| `frontend/.../Tasks.vue` / `TaskDetail.vue` | 轮询、取消/重试、状态展示 |
| `frontend/.../Datasets.vue` 等 | 发布需质检、正式任务门禁提示（WP03 配合） |
| `tests/test_task_worker.py` | claim 互斥、取消、重试、进度可见 |

---

### Task 1: 模型字段 + TaskService

- [ ] `EvalTask` 增加：`lease_owner`, `lease_until`, `fencing_token`, `cancel_requested`, `attempt`
- [ ] `database.py` 迁移列
- [ ] `task_service.py`：`enqueue`、`claim_next`（条件 UPDATE status queued→running）、`request_cancel`、`retry_task`（清结果或新 attempt）、环检测

### Task 2: Runner 可靠执行

- [ ] 每处理完 1 条样本：`commit`（或显式 session commit）使其它连接可见 progress/results
- [ ] 回写前校验 `fencing_token`；不匹配则停止
- [ ] 取消：读 `cancel_requested`（新 session 或 expire），退出为 `cancelled`，不标 success
- [ ] 启动时跳过已有 `EvalResult` 的 item_no（重启不重复）
- [ ] 依赖环：create/enqueue 时 BFS/DFS 拒绝

### Task 3: Worker 入口 + API

- [ ] `app/worker.py` 或 `python -m app.worker`：循环 `recover_expired` + `claim` + run
- [ ] `dispatch_queue` 改为走 claim（兼容 BackgroundTasks）
- [ ] `POST /tasks/{id}/retry`；`task_out` 暴露 lease/attempt/cancel_requested
- [ ] Agent 创建走 TaskService enqueue（若可小改）

### Task 4: 前端任务页

- [ ] `TaskDetail.vue`：取消、重试；轮询展示 progress/attempt/lease；结果列 execution_status/score_status
- [ ] `Tasks.vue`：运行中列表 3s 轮询；取消/重试入口；状态文案
- [ ] `api/index.js`：`retry` 方法

### Task 5: WP03 前端配合

- [ ] 创建任务表单：强调 `trial_run`、未发布/未质检禁用正式提交并提示
- [ ] 数据集：发布按钮在未质检时禁用或二次确认文案；条目修订后提示「已生成新版本」

### Task 6: 测试与交付

- [ ] `test_task_worker.py`：双 claim 仅一成功；取消不 success；retry 递增 attempt
- [ ] 全量 unittest + 前端构建或 lint 冒烟
- [ ] `docs/delivery/WP04.md` + STATUS

## Out of scope

- Redis/SSE 全量、多租户公平队列、完整 WorkItem 表拆分（本包用任务级 claim 满足验收核心）
