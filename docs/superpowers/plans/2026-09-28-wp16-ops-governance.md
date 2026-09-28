# WP16 运维制度与生态交付（含前端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.

**Goal:** 岗位/值班/变更/故障/漏洞制度与 FAQ；CONTRIBUTING + 许可/SBOM 清单；运维工单（负责人+闭环）；数据授权可追溯；运营报表；基准生态「已明确 vs 待业务定义」清单；演练留痕（AC46）；Ops 前端集成。

**Architecture:** `OpsTicket`/`OpsDrillRecord`/`DataAuthorization` + `ops_governance` 服务；扩展 `/api/ops/*`；文档落 `docs/operations/`；不虚构基准生态未定义承诺。

**Tech Stack:** FastAPI、SQLAlchemy、Vue3、unittest、Markdown 制度文档。

## Global Constraints

- 工单关闭必须有 `owner_id` 与 `resolution`；停用不删历史。
- 制度版本归档可检索；接口停用保留记录。
- 基准生态空白章节只列 TBD，不编造范围。

## File Map

| 路径 | 职责 |
|---|---|
| `models/ops_governance.py` | Ticket / Drill / Authorization |
| `services/ops_governance.py` | 状态机与报表 |
| `api/ops.py` | 工单/演练/授权/报表 API |
| `Ops.vue` + `api/index.js` | 运维台扩展 |
| `docs/operations/*` | 制度手册 |
| `CONTRIBUTING.md` / `LICENSE` / `docs/licenses/*` | 贡献与许可 |
| `tests/test_ops_governance.py` | AC46 级验收 |

## Tasks

1. 模型与服务 + API
2. 制度/贡献/许可文档
3. Ops 前端
4. 测试与交付
