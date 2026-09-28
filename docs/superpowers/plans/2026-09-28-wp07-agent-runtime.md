# WP07 持久化 Agent 运行时（含前端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or subagent-driven-development.

**Goal:** 会话级 AgentRun（lease/fencing/checkpoint/事件序）；工具选择→观察→回复循环；单 active run；限轮/预算/取消；断线后按 seq 续读；Agents 页可启停与回放。

**Architecture:** 轻量 `agent_runtime`（本会话不引入 LangGraph SDK）；`AgentRun`+`AgentEvent` 持久化；mock provider 保证确定性验收，live 走已有 model_client 可选；SSE/轮询共用事件表。

**Tech Stack:** FastAPI、SQLAlchemy、Vue3、unittest。

## Global Constraints

- 依赖 WP01/WP02/WP04；不改评测调度内部规则。
- 本会话不做：完整 LangGraph checkpointer、审批防重放（WP08）、子 Agent 委派（WP09）。

## File Map

| 路径 | 职责 |
|---|---|
| `models/agent.py` | AgentRun / AgentEvent；session.active_run_id |
| `services/agent_runtime.py` | create/claim/step/checkpoint/cancel/resume |
| `api/agents.py` | runs CRUD、events、SSE、cancel/resume |
| `frontend Agents.vue` + api | 运行面板、事件流、取消恢复 |
| `tests/test_agent_runtime.py` | 单 active、限轮、非法 schema、恢复 |

## Tasks

1. 模型 + 迁移
2. agent_runtime（mock 工具循环 + checkpoint）
3. API + SSE
4. 前端
5. 测试与交付
