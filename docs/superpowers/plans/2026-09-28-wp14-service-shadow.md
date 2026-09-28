# WP14 服务单用量与真实灰度（含前端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.

**Goal:** 报价快照版本、交付状态机（无报告不可 delivered）、幂等结算、影子双路评估四门禁、5% 流量与 7 天证据、原子转正/回滚；EvalServices UI 增强。

**Architecture:** `shadow_router` + `service_billing`；扩展 EvalServiceRequest；强化 `/api/services` 办理流转。

## Tasks

1. 影子门禁与幂等结算服务
2. API 状态机改造
3. EvalServices 前端
4. 测试与交付
