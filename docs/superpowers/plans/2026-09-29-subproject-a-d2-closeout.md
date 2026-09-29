# 子项目 A：D2 核心体验收尾 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户仅用表单即可注册并真实调用自建 HTTP 工具、两步 Skill 与自建 MCP（HTTP 与 stdio），每次调用留下可回查的脱敏证据，同时收紧测试隔离并修复 `database is locked`。

**Architecture:** 后端在现有统一网关 `invoke_tool` 上补齐证据字段、Skill 递归经网关、MCP 新传输层（`services/mcp/` 包）；独立进程 `tools/stats_service` 提供真实计算的 HTTP 与 MCP 服务；前端在 `Resources.vue` 的试用台、向导、MCP 工作台上接入这些接口，`SchemaForm` 改为无损。

**Tech Stack:** FastAPI 0.141 / Starlette 1.6、SQLAlchemy async + SQLite、httpx、unittest；Vue 3 + Element Plus、Vite、Node 22 `node --test`。

**Design spec:** `docs/superpowers/specs/2026-09-29-review-followup-roadmap-design.md`

## Global Constraints

- 测试一律先 `from tests import isolated_env`；绝不指向 `backend/eval_platform.db`。
- 后端命令在 `E:\eval-platform\backend` 执行，解释器 `.venv\Scripts\python.exe`，测试框架 `unittest`。
- 不修改业务库、不调用付费模型；AsyncMock/test double 只在隔离单测中使用，不能作为真实联调证据。
- 注册 Manifest 禁止明文凭证；凭证只用 `credential_ref`（环境变量名）。
- stdio MCP 只能引用服务端 `MCP_STDIO_ALLOWLIST` 中的别名，禁止 Manifest 携带 command/args。
- 新接口复用 `resource:view` / `resource:create` / `resource:invoke`；若出现新动作，同批完成 AGENTS.md 权限流程。
- 前端改动后运行 `npm run collect-permissions`、`npm run verify:ux-static`、`npm run build`。
- 产品页面文案不写“禁止 Mock 假成功”之类研发口号，写可操作的状态与下一步。
- 用户决定：当前分支 `fix/review-followup-d1` 的改动保持未提交；本计划各任务的 Commit 步骤改为“记录变更文件清单到任务勾选处”，除非用户另行要求提交。

## 分册

| 分册 | 任务 | 内容 |
|---|---|---|
| [part1-backend.md](2026-09-29-subproject-a-part1-backend.md) | Task 1–6 | 测试隔离、数据库锁、自建统计服务、调用证据与历史 API、Skill 经网关 |
| [part2-mcp.md](2026-09-29-subproject-a-part2-mcp.md) | Task 7–9 | MCP Streamable HTTP 传输与会话、stdio 白名单、探测落库与目录快照 |
| [part3-frontend.md](2026-09-29-subproject-a-part3-frontend.md) | Task 10–14 | 无损 SchemaForm、试用台、向导、MCP 工作台、全量回归与浏览器验收 |

任务按编号顺序执行；Task 3/4（统计服务）是 Task 6–9 集成测试的前置。

## 文件结构

| 路径 | 动作 | 职责 |
|---|---|---|
| `backend/tests/isolated_env.py` | 改 | 强制隔离路径 + `assert_isolated_database` |
| `backend/tests/test_isolation_guard.py` | 新 | A-ISO |
| `backend/app/api/tasks.py`、`backend/app/api/agents.py` | 改 | 写入全部提交后再登记后台任务 |
| `backend/tests/test_eval_flow.py` | 改 | 未配置 api_url 调用改为断言拒绝 |
| `tools/stats_service/{__init__,core,mcp_protocol,app,stdio_server}.py`、`run.ps1` | 新 | 自建真实计算服务 |
| `tools/stats_service/tests/{test_core,test_http}.py` | 新 | 服务自身单测 |
| `backend/tests/followup_helpers.py` | 新 | 登录、第二租户用户、统计服务子进程、Manifest 构造 |
| `backend/app/services/redaction.py` | 新 | 脱敏与证据摘要 |
| `backend/app/models/resource.py`、`backend/app/database.py` | 改 | ResourceCallLog 证据字段与迁移 |
| `backend/app/services/tool_gateway/__init__.py` | 改 | 证据落库、错误码透传、Skill 递归 |
| `backend/app/services/skill_runtime.py` | 改 | async `run_skill(step_invoker)`；MCP 远程分支转交 `services/mcp` |
| `backend/app/api/resources.py` | 改 | 调用历史、stdio 别名、Skill 步骤注册校验、probe 证据与目录 |
| `backend/app/services/protocol.py` | 改 | stdio MCP 注册校验 |
| `backend/app/services/mcp/{__init__,errors,http_transport,stdio_transport,session,runner,catalog}.py` | 新 | MCP 完整实现 |
| `backend/app/services/mcp_client.py` | 删 | 被 `services/mcp` 取代 |
| `backend/tests/test_review_followup_a.py` | 新 | A-REV07/08/09、A-MCP 集成测试 |
| `backend/tests/test_tool_gateway.py` | 改 | `run_skill` 异步签名；移除 `RemoteMcpClientTest` |
| `frontend/src/utils/schemaForm.js`、`frontend/tests/unit/schemaForm.test.mjs` | 新 | Schema 纯函数与单测 |
| `frontend/src/components/SchemaForm.vue` | 改 | 无损表单 |
| `frontend/src/components/StatusBadge.vue` | 改 | 增加 `blocked` |
| `frontend/src/api/index.js` | 改 | `calls`、`stdioAliases` |
| `frontend/src/views/Resources.vue` | 改 | 试用台、向导、MCP 工作台 |
| `frontend/package.json` | 改 | `test:unit` 脚本 |
| `docs/superpowers/evidence/subproject-a.md` | 新 | 验收证据（Task 14） |

## 后续子项目

B（业务库 Mock 清理）、C（真实数据填充）、D（全站 24 页）的范围与门禁见设计文档第 2 节。A 完成并验收后，分别走 brainstorming → writing-plans 出独立计划，不在本计划中实施。
