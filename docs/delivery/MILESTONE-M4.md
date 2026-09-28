# M4 里程碑收口（WP00–WP16）

日期：2026-09-28  
计划根：`docs/implementation-plan-2026-09-28`  
追踪：`docs/delivery/STATUS.md`

## 结论

> 2026-09-28 复审修正：下述“按包交付/工程项已落地”是历史交付方结论，不应视为全范围关闭。源码复审发现 WP07 live 仍走 Mock、WP14 客户端 score 仍进入门禁、WP11 非执行比对被表示为用例通过率、WP16 无证据可登记 pass。请以 [追加复审与整改入口](REVIEW-AND-FRONTEND-NEXT.md) 核对未关闭项；本次仅完成复审指导，未修复这些实现缺陷。

**研发工作包 WP00–WP16 已按包交付**（隔离 unittest + 前端 build 证据见各 `docs/delivery/WPxx.md`）。  
这表示设计包内的工程项已落地到可运行代码与制度文档，**不等于**原文两份规格的全量生产验收通过。

| 层级 | 状态 |
|---|---|
| L0/L1 契约与单测 | 基线通过（全量 discover，见 STATUS 末行计数） |
| L2 独立 PG/Redis/多 worker | 未作为默认交付；SQLite + 进程内队列为主 |
| L3 真实模型/证书/MCP/媒体联调 | **部分完成**：DeepSeek HTTPS + 本地 HTTP MCP 证据见 `L3-LIVE.md`；企业 mTLS/公有 MCP/媒体 live 仍开放 |
| L4 生产压测/混沌/组织签署 | 待生产容量与运营确认 |

## 新人入口（约 30 分钟）

1. 读根 `README.md` → `docs/operations/README.md` → `docs/operations/WP15-runbook.md`
2. 本地起后端/前端（开发可用 `admin`/`admin123`；**生产禁止**）
3. 打开 Ops：探针 → 备份 → 恢复演练 → 建工单闭环 → 看制度索引
4. 按 `docs/delivery/STATUS.md` 抽查最近 WP 交付报告中的「未做什么」

## 明确未关闭缺口（勿对外宣称已完成）

从各 WP「未做什么」与 O05 TBD 汇总（非穷尽）：

- 真实 LLM / 企业 mTLS / 外部 MCP 全链路联调
- Redis 共享限流、PostgreSQL、对象存储集群
- 1000 VU 榜单 / 500 RPS 网关等原文性能硬目标实测
- async/stream 任务子系统深度、完整 CycloneDX 漏洞门禁
- 14 行业完整题库与 ECO-TBD-*（见 `docs/operations/benchmark-ecosystem.md`）
- 外接 Jira/飞书；运营负责人线下签字

## 建议下一步（非 WP 编号）

1. ~~准备预发 + 真实模型/MCP 证据~~ → 见 `docs/delivery/L3-LIVE.md`（DeepSeek）
2. 轮换已暴露的 API Key；补企业 mTLS / 外部 MCP（若需要）
3. 组织按 runbook 做一次有签字的发布/回滚演练（AC46 人工段）
4. 业务关闭 ECO-TBD 或正式宣布「试点范围」边界
5. L4：容量压测与生产值班签署

## 回滚与制度

应用回滚见 WP15 runbook；制度与授权记录停用不删除。代码回退以 git 为准。
