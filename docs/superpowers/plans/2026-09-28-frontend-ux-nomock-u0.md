# Frontend UX + No-Mock U0–U5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.

**Goal:** 按复审 F01–F12 与 NO-MOCK 要求，先封住虚假 live/pass（U0），再推进交互基础与 Agent/工具中心（U1–U3），最后全站与验收记录（U4–U5）。trial = 真实小规模试跑，禁止 Mock/假成功回退。

**Architecture:** 后端门禁优先（无配置→明确失败；观测仅服务端持久化；演练 evidence 校验）；前端去掉写死 mock/常量分数/一键 pass；隔离测试证明负例。

**Tech Stack:** FastAPI、Vue3、Element Plus、unittest、现有 DeepSeek `.env`（不入库）。

## Global Constraints

- 不访问业务 `eval_platform.db`；测试用 `isolated_env`。
- 不把演示能力标正式 WP 关闭；STATUS 追加复审事实。
- 缺外部条件写 `blocked`，继续可做项。

## Phase Map

| Phase | Scope | Exit |
|---|---|---|
| **U0** | F01–F04、F10、model_client 无 url | 无假正式通过；负例测试绿 |
| U1 | F05–F07、六态/选择器 | 会话不串、MCP 来源互斥 |
| U2 | Agents 工作台第 4 节 | 真实规划模型 tool loop |
| U3 | Resources 第 5 节 | 向导/Schema/MCP/Skill |
| U4 | 其余 24 页 | 矩阵记录 |
| U5 | frontend-ux 证据 + STATUS | UX01–16 可复现或 blocked |

## U0 File Map

| 路径 | 改动 |
|---|---|
| `services/model_client.py` | 无 api_url 抛错；health ok=False |
| `services/agent_runtime.py` + Agents API | 删除 mock provider；真实 tools 循环 |
| `Agents.vue` | 选 live + 已配置规划模型；禁 mock |
| `services/shadow_router.py` + tasks shadow API | 拒绝请求体 score；服务端观测 |
| `EvalServices.vue` | 不提交硬编码分数 |
| `ops_governance` + Ops.vue | 无证据不得 pass |
| `models/resource` + resources API | 租户/对象范围（最小可测） |
| `scenario_simulators` + media_adapter | 缺候选 not_run；不做 reference 冒充 |

## U0 Tasks

1. model_client + task_runner 禁 mock 回退（测试）
2. F01 agent runtime live tool-calling（测试）
3. F02 shadow 服务端观测（测试）
4. F03 drill evidence gate（测试）
5. F04 resource/service 对象边界（最小迁移+测试）
6. F10 code/media not_run（测试）
7. `docs/delivery/frontend-ux/U0.md` + STATUS 追加

## Subsequent

U1–U5 在 U0 绿后按 `02-frontend-execution-guide.md` 分阶段开独立子计划，避免单次膨胀。
