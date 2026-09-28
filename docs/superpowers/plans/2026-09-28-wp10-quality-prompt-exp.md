# WP10 质量增强与提示词实验（含前端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or subagent-driven-development.

**Goal:** 质量规则补一致性/近重复与可解释 issue；修复出新版本并复检；PromptExperiment 开发/保留集隔离、配对统计、预算与无显著收益不自动发布。

**Architecture:** 扩展 `quality_checker`；fix 后可选 `recheck`；`prompt_experiment` 服务切分 holdout、仅 develop 优化、holdout 复算配对差。

**Tech Stack:** FastAPI、SQLAlchemy、Vue3、unittest。

## Global Constraints

- 依赖 WP03/WP02；保留集不对优化模型开放。
- 本会话不做：真实 LLM 批量生成候选、完整显著性检验库。

## File Map

| 路径 | 职责 |
|---|---|
| `services/quality_checker.py` | consistency / near_duplicate |
| `api/quality.py` | fix+recheck |
| `services/prompt_experiment.py` | 切分、配对、发布门禁 |
| `models/prompt.py` | PromptExperiment |
| `api/prompts.py` | experiment API |
| `Quality.vue` / `Prompts.vue` | UI |
| `tests/test_quality_prompt_exp.py` | 验收 |

## Tasks

1. 质量规则 + 修复复检
2. PromptExperiment
3. 前端
4. 测试与交付
