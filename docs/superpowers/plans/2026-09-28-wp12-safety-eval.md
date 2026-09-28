# WP12 四类安全可信评测（含前端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or subagent-driven-development.

**Goal:** 实现 risk / watermark / alignment / hallucination 正式 evaluator；受控自适应多轮；固定集与探索集分离；候选题双验证；专家复核 UI；空输出/缺证据/标识冒充门禁。

**Architecture:** `safety_eval` 承载规则版本化裁判与校准；夹具落盘 `fixtures/safety/`；API `/api/safety`；前端 `Safety.vue`；`builtin_tools` 委托正式裁判（去掉 demo_only 冒充正式资格）。

**Tech Stack:** FastAPI、Vue3、unittest。

## Global Constraints

- 空输出不得满分；reference 中的标识不能代替被测输出。
- 缺证据 → `undetermined`，不得判真。
- 规则版本变更需重新校准；探索集不得入固定比较。
- 不做自动法律合规结论。

## File Map

| 路径 | 职责 |
|---|---|
| `fixtures/safety/**` | 四类固定/探索样本与人工金标 |
| `services/safety_eval.py` | 四类 evaluator + 自适应 + 校准 |
| `services/builtin_tools.py` | 委托正式裁判 |
| `api/safety.py` | 评测/校准/复核/候选 |
| `frontend Safety.vue` | 专家复核与类别表现 |
| `tests/test_safety_eval.py` | 验收 |

## Tasks

1. 夹具与 safety_eval 核心
2. API + builtin 委托
3. 前端 + 权限路由
4. 测试与交付
