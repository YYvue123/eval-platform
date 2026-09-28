# WP13 可比榜单与证据报告（含美观前端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or subagent-driven-development.

**Goal:** 正式结果资格过滤、同 cohort 比较、冻结归一化、缺指标不填 0、并列、真实成本可复算；ReportJob 分格式状态与证据 ID；发布/回滚；Leaderboard 精密观测台风格 UI。

**Architecture:** 增强 `leaderboard`/`report_archive`；新增 `LeaderboardRelease`/`ReportJob`；API 扩展；前端 Leaderboard 重构视觉与 TaskDetail 报告状态。

**Tech Stack:** FastAPI、Vue3、Element Plus、ECharts、unittest。

## Global Constraints

- mock/trial/simulation/评分错误不得入正式榜。
- 不同 dataset/judge 版本不得混排。
- 缺数据展示 null，不填 0。
- 历史快照不可变；回滚展示上一合格发布。

## File Map

| 路径 | 职责 |
|---|---|
| `models/eval_task.py` | Release / ReportJob |
| `services/leaderboard.py` | 资格/cohort/冻结/并列 |
| `services/report_archive.py` | 分格式状态 + 证据 |
| `api/tasks.py` leaderboard/report | API |
| `Leaderboard.vue` / `TaskDetail.vue` | 美观 UI |
| `tests/test_leaderboard_reports.py` | 验收 |

## Tasks

1. 模型与榜单/报告服务
2. API
3. 前端视觉
4. 测试与交付
