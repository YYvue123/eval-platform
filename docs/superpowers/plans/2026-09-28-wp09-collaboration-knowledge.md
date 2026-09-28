# WP09 专项协作与可信知识（含前端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or subagent-driven-development.

**Goal:** 按需委派 monitor/diagnose/review（简单任务不全开）；delegation 深度/并行上限；监控摘要 hash 去重；诊断带证据；恢复回主审批；知识候选审核入库；检索强制租户+过期过滤；Agents 证据/子任务视图。

**Architecture:** `collaboration.py` 决定角色；`AgentDelegation`/`AgentMonitorState`/`KnowledgeCandidate` 持久化；子 Agent 工具白名单无写任务；`search_knowledge` 可信检索前置。

**Tech Stack:** FastAPI、SQLAlchemy、Vue3、unittest。

## Global Constraints

- 依赖 WP08；子 Agent 禁止 create_task/enqueue。
- 本会话不做：真实 LLM 子图、向量索引、完整并行编排引擎。

## File Map

| 路径 | 职责 |
|---|---|
| `models/agent.py` | Delegation / MonitorState / KnowledgeCandidate |
| `services/collaboration.py` | 委派策略、深度/并行、合并 |
| `services/knowledge_trust.py` | 候选、审核、可信检索 |
| `api/agents.py` | delegate / review knowledge / evidence |
| `frontend Agents.vue` | 子任务与证据 |
| `tests/test_collaboration.py` | 验收 |

## Tasks

1. 模型 + 委派策略
2. 监控去重 + 诊断证据
3. 知识候选审核 + 租户检索
4. 前端
5. 测试与交付
