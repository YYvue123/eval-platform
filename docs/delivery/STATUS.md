# WP 验收状态追踪（追加）

> 用户追加要求：所有业务流程（含 trial/工具试用）删除 Mock、固定假结果和成功回退，缺少依赖必须明确阻塞；见 [真实实现硬要求](NO-MOCK-REAL-IMPLEMENTATION.md)。本轮已完成文档复审，代码整改待实施。

> 2026-09-28 U0 补充：F01 Agent mock、F02 客户端影子分数、F03 无证据演练 pass、F10 参考解冒充已整改（见 `frontend-ux/U0.md`）。U1–U5 已交付文档与代码门禁；**浏览器 UX01–16 多数仍 not_run**；WP06/07/11/14/16 仍需按复审分层，不得仅凭历史「全量 tests OK」视为原范围关闭。

相对核查包 `docs/implementation-plan-2026-09-28` 的追加记录，**不覆写**原始差距矩阵事实。

| 日期 | 工作包 | 验收状态 | 证据 |
|---|---|---|---|
| 2026-09-28 | WP00 | 本包目标项已实现并通过隔离 unittest；真实模型/生产并发未验证 | `docs/delivery/WP00.md` |
| 2026-09-28 | WP01 | 租户隔离+对象范围+禁用用户+敏感导出权限已实现；全量 32 tests OK；部分非核心读接口待继续收口 | `docs/delivery/WP01.md` |
| 2026-09-28 | WP02 | 信封1.3+tool_gateway+幂等+ResourceVersion+HTTP429/trace；runner 经网关；全量 38 tests OK；async/stream/Redis 未做 | `docs/delivery/WP02.md` |
| 2026-09-28 | WP03 | 数据集修订出新版本、模型 AccessConfig 冻结、正式门禁、health 2xx、生产禁 plain；全量 43 tests OK；前端/xls/凭证轮换未做 | `docs/delivery/WP03.md` |
| 2026-09-28 | WP04 | claim/lease/fencing+逐样本提交+取消/重试+worker；前端任务轮询/取消重试与 WP03 门禁 UI；全量 47 tests OK + frontend build | `docs/delivery/WP04.md` |
| 2026-09-28 | WP05 | batch 绑定/分片守卫/幂等/预算 paused_budget/GC 保护；前端批次状态与任务费用；全量 54 tests OK + build | `docs/delivery/WP05.md` |
| 2026-09-28 | WP06 | HTTP MCP + Skill `$ref` + side_effects stub/egress；Resources 探测 UI；全量 65 tests OK + build | `docs/delivery/WP06.md` |
| 2026-09-28 | WP07 | AgentRun/事件序/checkpoint/lease；单 active；限轮预算；Agents Runtime UI；全量 77 tests OK + build | `docs/delivery/WP07.md` |
| 2026-09-28 | WP08 | GoalSpec/澄清/硬过滤/审批 hash 防重放/ACL；Agents 审批工作台；全量 84 tests OK + build | `docs/delivery/WP08.md` |
| 2026-09-28 | WP09 | 按需委派/深度并行/监控去重/诊断证据/知识候选审核；Agents 子任务证据；全量 92 tests OK + build | `docs/delivery/WP09.md` |
| 2026-09-28 | WP10 | 质量一致性/近重复/修复复检；PromptExperiment holdout 门禁；全量 97 tests OK + build | `docs/delivery/WP10.md` |
| 2026-09-28 | WP11a | 基准/指标注册、readiness 门禁、MUT 工具隔离、Benchmarks 页 | `docs/delivery/WP11.md` |
| 2026-09-28 | WP11 | 11a–f 全包：文本金标/媒体 fixture/MUT oracle/金融政务/轻量模拟器；全量 118 tests OK + build | `docs/delivery/WP11.md` |
| 2026-09-28 | WP12 | 四类安全评测+校准≥90%+专家复核UI；全量 130 tests OK + build | `docs/delivery/WP12.md` |
| 2026-09-28 | WP13 | 可比榜单/cohort/冻结尺度/发布回滚/证据报告；观测台风格前端；全量 138 tests OK + build | `docs/delivery/WP13.md` |
| 2026-09-28 | WP14 | 服务单幂等结算/影子四门禁/转正回滚；榜单配色对齐主题；全量 146 tests OK + build | `docs/delivery/WP14.md` |
| 2026-09-28 | WP15 | live/ready、生产凭证门禁、AdmissionRunner、恢复演练 RPO/RTO、故障注入、镜像/SBOM/CI、Ops 台；全量 154 tests OK + build | `docs/delivery/WP15.md` |
| 2026-09-28 | WP16 | 运维制度/贡献许可、工单闭环、演练留痕、数据授权、运营报表、基准生态 TBD；全量 157 tests OK + build | `docs/delivery/WP16.md` |
| 2026-09-28 | M4 收口 | WP00–WP16 工程包闭环；L3/L4 与 ECO-TBD 仍开放 | `docs/delivery/MILESTONE-M4.md` |
| 2026-09-28 | L3 DeepSeek | staging + DeepSeek 双模型直连/平台 trial + 本地 HTTP MCP；证据包 ok | `docs/delivery/L3-LIVE.md` |
| 2026-09-28 | U0 No-Mock | F01–F04/F10：禁 mock agent、影子仅服务端观测、演练证据门禁、资源/服务单租户字段、代码/媒体 not_run；隔离单测通过 | `docs/delivery/frontend-ux/U0.md` |
| 2026-09-28 | U1 交互基础 | F05–F07：会话 generation 隔离、轮询单飞/事件去重/写锁、MCP 来源互斥；mcp_probe 负例单测 | `docs/delivery/frontend-ux/U1.md` |
| 2026-09-28 | U2 Agent 工作台 | 第 4 节：会话轨+产品态主动作+ResourcePicker+动态澄清+高级 Tab；build 通过 | `docs/delivery/frontend-ux/U2.md` |
| 2026-09-28 | U3 工具中心 | 第 5 节：Tab/分页/详情、注册向导、Schema 试用台、MCP 三态工作台；build 通过 | `docs/delivery/frontend-ux/U3.md` |
| 2026-09-28 | U4 全站矩阵 | 24 页覆盖表；Dashboard/Tasks/Models/Safety/EvalServices/路由回退重点收口；浏览器 UX not_run | `docs/delivery/frontend-ux/U4.md` |
| 2026-09-28 | U5 验收交接 | 权限采集+ux-static；隔离回归 63 OK；F/UX/AC 映射诚实标注；浏览器 UX 多数 not_run | `docs/delivery/frontend-ux/U5.md` |
| 2026-09-28 | UX 烟雾 e2e | Playwright 脚手架；隔离库+Vite；7 passed（登录/工作台/Tasks/Models/Safety/Services/MCP 互斥） | `docs/delivery/frontend-ux/UX-SMOKE.md` |
