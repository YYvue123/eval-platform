# WP08 规划澄清与防重放审批（含前端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or subagent-driven-development.

**Goal:** GoalSpec + 澄清缺口；资源硬过滤；计划 canonical hash；审批有效期与消费幂等；确认创建任务统一走 TaskService 规则（含模型 ACL）；Agents 计划/审批工作台。

**Architecture:** `goal_spec` 产出目标与澄清；`draft_plan` 硬过滤数据集/模型；`approval_service` 签发/校验/消费；confirm 幂等只创建一个 experiment。

**Tech Stack:** FastAPI、SQLAlchemy、Vue3、unittest。

## Global Constraints

- 依赖 WP07/WP03；Agent 创建任务不得绕过常规 ACL/门禁。
- 本会话不做：完整 LLM 多轮澄清对话、复杂 DAG 调度器、WP09 子 Agent。

## File Map

| 路径 | 职责 |
|---|---|
| `services/goal_spec.py` | GoalSpec、澄清、canonical_hash |
| `services/approval_service.py` | 审批签发/过期/消费幂等 |
| `services/agent_orchestrator.py` | 硬过滤 + gaps |
| `models/agent.py` | AgentApproval |
| `api/agents.py` | clarify / approve / confirm 幂等 |
| `frontend Agents.vue` | 计划/澄清/审批工作台 |
| `tests/test_agent_approval.py` | 验收 |

## Tasks

1. GoalSpec + 硬过滤 + hash
2. AgentApproval + 消费幂等
3. confirm 统一入口 + ACL
4. 前端
5. 测试与交付
