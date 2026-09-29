# D Task 3：403 与口号

Work from E:\eval-platform. No git commit. TDD. Do not start Task 4.

## 1. Router 无权限 → NotFound

`frontend/src/router/index.js`：`to.meta.permission` 不满足时一律：

```javascript
next({
  path: '/not-found',
  query: { reason: 'forbidden', from: to.fullPath },
})
```

删除把无权限用户送到 `firstAccessiblePath` + `query.denied` 的逻辑（含 dashboard 特例）。登录未登录仍走 `/login?redirect=`。已登录访问 `/login` 仍 `safeHomePath`。

若尚无显式 `/not-found` 路由，在 catch-all 之前加一条指向现有 `NotFound.vue`（MainLayout 子路由即可），避免只靠 `/:pathMatch(.*)*`。

## 2. NotFound.vue 403 文案

当 `route.query.reason === 'forbidden'` 时显示 403（标题含无权/没有权限，说明联系管理员或回可访问工作台）。可同时兼容旧 `query.denied`。`from` 仅用于展示或回跳，不要 XSS。

## 3. Agents 口号与规划模型必选

page-desc 改为精确：`描述目标、核对计划、批准后执行；执行状态以服务端为准。`

删除「无 Mock」产品口号。试用开关文案去掉「非 Mock」，改为如：`开启后按小规模真实样本执行，用量计入同一预算。`

删除 `plannerModels.value[0].id` 自动选中。无用户选择时 `plannerModelId` 保持空。规划模型选择器 placeholder 或旁注「必选」。`生成计划` 在未选规划模型时 disabled。`createSession` 未选模型时不得静默用第一项。

## 4. Models.vue

field-hint 改为精确：`未配置 api_url 时无法探测或试调用。`

不得出现「不会回退到本地 Mock」或「留空则使用本地 Mock」。

## 5. verify-ux-static.mjs

- 仍 error：`留空则使用本地 Mock`
- **删除**对「不会回退到本地 Mock」的强制匹配
- **改为**若 Models.vue 不含 `无法探测或试调用` 则 **error**（不是 warning）
- router 仍须引用 `safeHomePath` 或 `firstAccessiblePath`（登录回跳可保留 firstAccessiblePath 的 import 若仍用；若不再用 firstAccessiblePath 于 router，确保 Login/NotFound/router 至少一处命中现有静态检查）

## 6. Tests

`frontend/tests/unit/forbiddenNav.test.mjs`（或扩 listQuery.test）：源码断言
- router 导航 `/not-found` + `reason: 'forbidden'`
- 不再 `query: { denied:`
- Agents 无 `plannerModels.value[0]`
- Agents page-desc 新文案
- Models 新 hint；无 Mock 回退句
- verify-ux-static 源码含 `无法探测或试调用` 且不含把「不会回退到本地 Mock」当通过条件

Dashboard 上 `route.query.denied` 的 banner 可保留作兼容，但新导航不再写该 query。

## Verify

cd frontend; npm run test:unit
npm run verify:ux-static

Report `.superpowers/sdd/task-d3-report.md`
