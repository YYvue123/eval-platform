# WP11b–f 场景金标包与模拟器（含前端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or subagent-driven-development.

**Goal:** 补齐 WP11 剩余切片：文本五场景金标+校准、媒体真实 URI、MUT episode/oracle、金融/政务行业包、轻量模拟器；门禁通过的套件可达 ready；前端可浏览样本与模拟器状态。

**Architecture:** 夹具与校准报告落盘于 `backend/app/fixtures/benchmarks/`；`benchmark_packs` 加载并校验；`media_adapter` / `mut_oracle` / `scenario_simulators` 提供执行侧能力；`benchmark_registry.default_suites` 指向真实资源后标 ready。

**Tech Stack:** FastAPI、SQLAlchemy、Vue3、unittest。

## Global Constraints

- 代码评测禁止宿主执行；仅沙箱/oracle 裁决。
- 媒体必须有可解析 URI/文件，禁止字符串描述冒充。
- MUT 禁止平台管理工具；最终状态由独立 oracle 验证。
- 不可观测指标保持 `not_observable`。
- 行业仅交付金融/政务试点；其余行业保持 draft。

## File Map

| 路径 | 职责 |
|---|---|
| `fixtures/benchmarks/**` | 金标样本、媒体资产、校准报告 |
| `services/benchmark_packs.py` | 加载/校验场景包 |
| `services/media_adapter.py` | 媒体 URI 解析与校验 |
| `services/mut_oracle.py` | Episode 环境 + 最终状态 oracle |
| `services/scenario_simulators.py` | 代码/表格/Agent 轻量模拟器 |
| `services/benchmark_registry.py` | 套件 readiness 升级 |
| `api/benchmarks.py` | packs / simulate / media 校验 API |
| `frontend Benchmarks.vue` + api | 样本与模拟器面板 |
| `tests/test_benchmark_packs.py` | 11b–f 验收 |

## Tasks

1. 夹具与 packs 加载器（11b/e）
2. 媒体适配器（11c）
3. MUT oracle（11d）
4. 模拟器（11f）
5. Registry + API + FE
6. 测试与 WP11 全包交付
