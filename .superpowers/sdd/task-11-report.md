# Task 11 实施报告：试用台接入服务端调用历史

## Status

完成。试用台通过 `resourcesApi.calls` 拉取真实调用历史；成功判定改为
`status === 'success' && !error`；未知服务端耗时显示「—」而非 0。未实现
Task 12 向导 / Task 13 MCP 工作台，未创建 commit。

## TDD 记录

### RED

命令：

```powershell
cd E:\eval-platform\frontend
npm run test:unit
```

输出：

```text
Error [ERR_MODULE_NOT_FOUND]: Cannot find module
'E:\\eval-platform\\frontend\\src\\utils\\resourceTrial.js'
not ok 1 - tests\\unit\\resourceTrial.test.mjs
# tests 6
# pass 5
# fail 1
```

失败原因符合预期：`resourceTrial.js` 尚不存在。

### GREEN

命令：

```powershell
cd E:\eval-platform\frontend
npm run test:unit
npm run verify:ux-static
npm run build
```

`test:unit`：

```text
# tests 11
# pass 11
# fail 0
```

`verify:ux-static`：`[verify:ux-static] OK`（routes sampled=20, warnings=0）

`build`：`✓ 2296 modules transformed.` / `✓ built in 18.88s`

## What you implemented

- `resourcesApi.calls(id, params)` → `GET /resources/calls/:id`（baseURL 已含 `/api`）。
- 试用结果：正向成功；`latency_ms` 初始为 null，加载历史后用匹配项的
  `latency_ms`；文案为「服务端执行耗时」「浏览器等待耗时」。
- `SchemaForm.validate()` 失败展示 `errors` 第一条。
- 最近调用：加载 / 空 / 失败分开展示；catch 不把 `items` 伪装成 `[]`。
- `StatusBadge` 增加 `blocked`（已阻断）；`blocked`/`denied` 不映射为 completed。
- 试用对话框宽度 `min(900px, calc(100vw - 24px))`；宽屏 12/12，窄屏 24；
  历史表独立横向滚动。

## Files

- Create: `frontend/src/utils/resourceTrial.js`
- Create: `frontend/tests/unit/resourceTrial.test.mjs`
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/views/Resources.vue`
- Modify: `frontend/src/components/StatusBadge.vue`

## Concerns

- 试用对话框需登录后才能在浏览器点通；本次以单测 + 静态门禁 + production build 验证。
- HTTP 层失败时 axios 拦截器仍可能 toast，历史区另有错误条，不伪装为空列表。

## Follow-up（Important：禁止 list[0] 回退）

`pickHistoryLatency` 仅在 `correlation_id` 精确匹配时返回 `latency_ms`；不匹配、无 id、空列表均返回 `null`，UI 显示「—」。未改 `Resources.vue` 向导/D2 代码，未 commit。

`npm run test:unit`（frontend）：`# tests 11` / `# pass 11` / `# fail 0`
