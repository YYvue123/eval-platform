# Task 14 实施报告：全量隔离回归与浏览器证据

## Status

**DONE_WITH_CONCERNS**

复审（Needs fixes）本轮已改产品文案并重拍与 caption 不符的截图。未创建 commit。未触碰 `backend/eval_platform.db`。未结束非本轮进程。本轮启动了隔离栈 8765 / 8001 / 5174（此前已停）。

## Fix round（review findings）

1. `frontend/src/views/Resources.vue`
   - `page-desc`：去掉「真实调用，无 Mock 假成功。」改为「发现、注册并试用工具、Skill 与 MCP；试用台可查看最近调用。」
   - 详情 Alert：去掉「API 未完整开放 / 静态假数据」，改为「版本列表尚未接入；调用记录请在试用台查看最近调用。」
   - 未改 `Agents.vue` / `Models.vue`
2. `npm run verify:ux-static`（frontend/）：OK，`routes sampled=20 nav=13 warnings=0`，55 权限码
3. 证据诚实：替换 `a-ui-parse-fail-390.png`（试用台缺参失败）、`a-ui-parse-history-refresh-1440.png`（刷新后 4 条）；新增/替换 `a-ui-mcp-stdio-call-1440.png` 与 `a-ui-mcp-stdio-listed-1440.png`（五步条「最近调用成功」）。试用台无 `source` 列，`skill_step` 以 `GET /api/resources/calls/demo%2Fparse_ui` JSON 为准。

## Commands

```text
# 复审文案后
cd frontend && npm run verify:ux-static

# 隔离栈（本轮重启）
tools\stats_service\run.ps1
DATABASE_URL=...a_ui.db uvicorn --port 8001
npx vite --config vite.a-ui.config.js --host 127.0.0.1 --port 5174
```

## Suite summaries

| Suite | Count | Time | Result |
|---|---|---|---|
| Backend focused | Ran **81** tests | **75.696s** | OK（前半段，本轮未重跑 discover） |
| Backend discover | Ran **208** tests | **157.301s** | OK；无 `database is locked` |
| Frontend unit | **34** pass / 0 fail | — | 前半段 |
| collect-permissions | **55** 码 | — | 文案轮随 verify 再跑 |
| verify:ux-static | OK | — | **文案修改后再跑** |
| build | ~18s | — | 前半段 |

## Browser A-UI（复审重拍）

- URL：`http://127.0.0.1:5174`，登录 `admin`
- 缺参失败：`demo/parse_ui` `trial-1790624471758` / `trace_id=254b863d78a84ec2b900437dbbed155c`，`status=failed`
- 刷新历史：试用台 4 条；skill_step 仅 API：`source=skill_step`，`parent_correlation_id=trial-1790623722560`
- MCP stdio parse：`trace_id=7b8bf485b76b448ab8be93d065f9a7cc`，工作台「最近调用成功」

## Files

- Modify: `frontend/src/views/Resources.vue`
- Update: `docs/superpowers/evidence/subproject-a.md`
- Replace/add PNGs: `a-ui-parse-fail-390.png`、`a-ui-parse-history-refresh-1440.png`、`a-ui-mcp-stdio-call-1440.png`、`a-ui-mcp-stdio-listed-1440.png`
- Update: `.superpowers/sdd/task-14-report.md`

## Concerns

1. 计划默认端口 8000/5173 仍被占用；隔离栈 **8001 / 5174**，统计 **8765**。
2. 试用台历史无 `source` 列，不能靠截图证明 `skill_step`。
3. 可选「未裁切 MCP HTTP 五步条」本轮未另拍。
4. 浏览器截图分辨率受 IDE 面板约束；390 图用 `Emulation.setDeviceMetricsOverride` 后拍摄。
5. 工作区曾有并行改写 `Resources.vue` 文案；落盘以用户指定句为准。
6. 隔离进程仍在运行；未结束占用 8000/5173 的进程。

## Self-review

- [x] 口号缺陷记为已修复，不声称 Mock 口号抽检通过
- [x] 390 失败图为试用台而非详情抽屉
- [x] skill_step / parent 有真实 API excerpt
- [x] stdio 截图为调用成功后的五步条
- [x] 无 commit

## Review follow-up note (2026-09-29)

复审 Critical 文案：`Resources.vue` 已换成操作说明（页眉「发现、注册并试用工具 / Skill / MCP；调用结果与最近记录在试用台查看。」Alert「版本时间线尚未接入本页；调用记录请打开试用台查看。」）。未改 Models.vue。`verify:ux-static` OK。

复审 Important 截图：`a-ui-parse-fail-390.png` 为试用台缺参失败；`a-ui-parse-history-3-1440.png` 为 4 行历史（旧图 2 行作废）；stdio `a-ui-mcp-stdio-call-1440.png` 为 parse 后「最近调用成功」五步条。converted/mean/skill_step 以 calls API 为准。MCP 五步条默认横向会裁切，复拍时临时纵向。未 commit，未动 `eval_platform.db`，未杀 8000/5173。
