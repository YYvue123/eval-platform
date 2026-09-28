# 变更 / 发布 / 故障 / 漏洞流程

版本：2026-09-28-wp16

## 变更与发布

1. 提交变更说明（目的、影响面、回滚点、备份 sha256）。
2. CI 绿：全量 unittest + 前端 build + SBOM。
3. 按 [WP15-runbook](./WP15-runbook.md) 执行金丝雀/滚动。
4. `POST /api/ops/admission/run`；证据归档。
5. `POST /api/ops/drills` 记录 `drill_type=release`（AC46 留痕）。

失败：切回旧 upstream；**不**自动 downgrade 已写新数据。开 `category=change` 工单跟踪。

## 故障响应

1. 确认影响：`/api/live` vs `/api/ready`、降级标志、告警策略。
2. 开 `category=incident` 工单，**必须指定 owner_id** 后方可进入处理/关闭。
3. 缓解：故障注入仅用于演练；生产异常用备份/回滚/限流。
4. 关闭时填写 `resolution`；事后复盘链到工单 id。

## 漏洞流程

1. 受理 → `category=vuln` 工单，severity 按 CVSS/业务影响。
2. 限制对外披露直至补丁或缓解上线。
3. 依赖漏洞对照 `docs/licenses/THIRD_PARTY.md` 与 `sbom.json`。
4. 修复后回归相关 WP 测试；工单闭环。

## 回滚制度本身

制度文件变更提交 git；旧版本保留在历史提交。API `policy.version` 递增。**禁止删除**已关闭工单与演练/授权历史行（仅 `disabled`）。
