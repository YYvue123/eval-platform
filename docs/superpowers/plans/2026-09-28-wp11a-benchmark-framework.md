# WP11a 基准框架与 readiness（含前端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or subagent-driven-development.

**Goal:** metric/suite 注册表；场景 input schema / oracle / license / 校准门禁；task_catalog readiness；MUT 禁平台管理工具；媒体字符串输入不得标 ready；基准管理页。

**Architecture:** `benchmark_registry` 定义指标与套件；`BenchmarkSuite` 持久化 readiness；API 暴露列表/门禁；前端 Benchmarks 页；11b–11f 场景包本会话仅注册骨架。

**Tech Stack:** FastAPI、SQLAlchemy、Vue3、unittest。

## Global Constraints

- 依赖 WP05/WP06；缺资源不阻塞框架，但不能宣布全包 ready。
- 本会话不做：完整媒体适配、Docker 代码沙箱、行业全量数据、专用模拟器。

## File Map

| 路径 | 职责 |
|---|---|
| `services/benchmark_registry.py` | 指标/套件/readiness/MUT 策略 |
| `models/eval_task.py` 或独立 | BenchmarkSuite |
| `api/benchmarks.py` | 列表与门禁 |
| `frontend Benchmarks.vue` | 管理页 |
| `tests/test_benchmark_framework.py` | 验收 |

## Tasks

1. Registry + readiness
2. API + seed
3. 前端
4. 测试与交付
