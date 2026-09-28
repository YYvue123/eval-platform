# WP15 生产加固与完整验收（含前端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.

**Goal:** 真实 liveness/readiness、生产默认凭证门禁、AdmissionRunner（禁写死 True）、备份恢复演练测 RPO/RTO、可控故障注入、镜像/SBOM/CI 加固、Ops.vue 运维台与运行手册。

**Architecture:** `prod_guards` 启动校验；`degrade` 进程内降级标志；`admission` 实测项生成证据；`backup.restore_drill`；Ops API 扩展 live/ready/admission/fault；前端运维台。

**Tech Stack:** FastAPI、Vue3、Element Plus、Docker、unittest、GitHub Actions。

## Global Constraints

- 未实测项 `ok=null`/`status=unknown`，禁止常量 True 冒充通过。
- `APP_ENV=production` 禁止默认 SECRET_KEY 与默认 admin123 引导。
- readiness 失败返回 503；liveness 仅表示进程存活。
- 故障注入仅 ops 权限，默认可恢复。

## File Map

| 路径 | 职责 |
|---|---|
| `services/prod_guards.py` | 生产密钥/引导密码门禁 |
| `services/degrade.py` | DB/证书降级标志 |
| `services/admission.py` | 基础/完整准入 runner + 证据 |
| `services/backup.py` | restore_drill + hash |
| `api/ops.py` | live/ready/admission/fault/restore |
| `main.py` / `database.py` / `config.py` | 启动门禁与引导密码 |
| `deploy/Dockerfile` / `docker-compose.yml` / README | 镜像、金丝雀、探针 |
| `.github/workflows/ci.yml` | 全量单测 + SBOM |
| `Ops.vue` + `api/index.js` | 运维台 |
| `docs/operations/WP15-runbook.md` | 发布/回滚/恢复 |
| `tests/test_prod_hardening.py` | AC44/AC45 级验收 |

## Tasks

1. 后端门禁 / admission / backup / ops API
2. 部署制品与 CI
3. Ops 前端
4. 测试与交付文档
