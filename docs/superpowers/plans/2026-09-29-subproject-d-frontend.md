# 子项目 D：D3 全站 24 页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** 公共六态、URL 分页筛选、禁止 catch 空数组、去掉产品口号，并按 02 规格补各页流程缺口。

**Architecture:** 先落地 `asyncState` + `PageAsyncState` + `listQuery` + request `skipErrorToast` + 403→NotFound，再分批改页面。

**Tech Stack:** Vue 3、Vue Router、Element Plus、现有组件。

## Global Constraints

- 不写 Mock/假成功/API 未开放口号。
- `npm run test:unit`、`collect-permissions`、`verify:ux-static`、`build`。
- 不创建 commit。
- 新权限走 AGENTS.md；本计划尽量不新增动作。
- Models.vue 若去掉「不会回退到本地 Mock」，必须同步改 `frontend/scripts/verify-ux-static.mjs` 断言为新文案。

## 文件（公共）

| 路径 | 动作 |
|---|---|
| `frontend/src/utils/asyncState.js` | 新 |
| `frontend/src/utils/listQuery.js` | 新 |
| `frontend/src/components/PageAsyncState.vue` | 新 |
| `frontend/src/utils/request.js` | 改 skipErrorToast |
| `frontend/src/router/index.js` | 无权限 → NotFound |
| `frontend/tests/unit/asyncState.test.mjs` | 新 |
| `frontend/tests/unit/listQuery.test.mjs` | 新 |
| `docs/superpowers/evidence/subproject-d.md` | 新 |

---

### Task 1：六态纯函数 + PageAsyncState

`deriveAsyncState({loading, error, forbidden, items, createdOnce})` → `loading|error|forbidden|empty|uncreated|success`。

`empty`：已请求且数组空且 createdOnce。`uncreated`：从未成功加载过资源集合且空。

单测覆盖六分支。组件显示标题+下一步，不用颜色作为唯一状态。

`verify:ux-static` 仍须通过。

---

### Task 2：listQuery 与 request 静默

`readListQuery(query)` → `{page, page_size, q, status}`；`writeListQuery(router, patch)` 合并 query。

`request.js`：config `skipErrorToast: true` 时不 `ElMessage.error`。NotificationCenter 轮询使用该旗标。

禁止模式：文档注明页面 catch 不得 `items=[]` 而不设 error。本任务改 `Dashboard.vue`、`Agents.vue` 模型列表、`NotificationManage.vue` 受众 catch。

---

### Task 3：403 与口号

无权限：`router` 导航到 `/not-found?reason=forbidden&from=`。NotFound 展示 403 文案。

Agents 页描述改为「描述目标、核对计划、批准后执行；执行状态以服务端为准。」

Models 提示改为「未配置 api_url 时无法探测或试调用。」更新 `verify-ux-static.mjs`：删除对「不会回退到本地 Mock」的强制匹配，改为匹配「无法探测或试调用」；仍拒绝「留空则使用本地 Mock」。

Agents 规划模型：无用户选择时保持空并提示必选，不取 `items[0]`。

---

### Task 4：列表页分页与 URL

Datasets、Tasks、Quality、Prompts、EvalServices、Users、AuditLog：服务端分页 UI（即使 total 小也保留 pager 或显示「第 x 页」）；`page/q/status` 写入 `route.query`。Quality/Prompts/EvalServices 去掉「只拉 50 条当全量」。

ResourcePicker：滚动或「加载更多」请求下一页。

EmptyState + PageAsyncState 接入这些列表。

---

### Task 5：详情与其余页

TaskDetail 结果分页；DatasetDetail 失败态。Dashboard 失败分区。Leaderboard 去掉独立皮肤差异（用页面变量色）、加载/失败态。TaskTemplates 保留目录但加空态。Benchmarks/Safety/Ops/RolePermission/NotificationManage/ApiDocs/Profile/Login：PageAsyncState 或等价失败/空态；Audit 导出若已有 API 则接按钮，无则 disabled+「当前环境未开放导出」**不是**「API 未完整开放」。

Users：禁用按钮若 API 有 status 字段则接；无邀请 API 则不造邀请。

---

### Task 6：证据

`docs/superpowers/evidence/subproject-d.md`：每页六态抽检、1440/1024/390 至少各一组截图（Login、Resources、Agents、Tasks）。`npm run test:unit && npm run verify:ux-static && npm run build`。
