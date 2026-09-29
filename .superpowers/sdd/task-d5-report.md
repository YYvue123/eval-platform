# Task D5 报告：详情与其余页

## 状态

**DONE** — `frontend` `npm run test:unit` **65/65 pass**；`npm run verify:ux-static` **OK**；未 commit。未启动 Task 6。未做浏览器端到端交互抽检（验证按简报为单测 + 静态 UX 门）。

## RED

**命令：**

```powershell
cd E:\eval-platform\frontend
npm run test:unit
```

**关键输出：**

```
# tests 65
# pass 58
# fail 7
```

**失败原因：** `remainingPages.test.mjs` 已要求 TaskDetail 结果分页、DatasetDetail `loadError` 且去掉 `itemTotal > itemPageSize`、Leaderboard `page-header`/`PageAsyncState`、AuditLog 禁用导出文案、Users `status: 'disabled'`、Login catch 写表单错误、其余页 `PageAsyncState`+`loadError`；当时源码仍是旧详情/观测台皮肤与空 catch（TDD 预期 RED）。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\frontend
npm run test:unit
npm run verify:ux-static
```

**结果：** `tests 65` — **pass 65 / fail 0**；`[verify:ux-static] OK`（`routes sampled=20 nav=13 warnings=0`）。

| 用例 | 说明 |
| --- | --- |
| TaskDetail results… | `results({ page, page_size })` 读 `total`；`loadError` + `PageAsyncState`；常显 pager |
| DatasetDetail… | `loadError`；去掉 `itemTotal > itemPageSize`；样本 pager / 「第 x 页」常显 |
| Leaderboard… | `page-header` + `PageAsyncState` + `el-card`/`el-table`/`el-button` |
| AuditLog… | 禁用导出按钮文案 `当前环境未开放导出`；禁止「API 尚未完整开放」 |
| Users.vue disable… | `usersApi.update(id, { status: 'disabled' })`，权限 `user:edit` |
| Login.vue catch… | `displayMsg` 写在表单上，不再空 catch |
| remaining list-like… | 模板/基准/安全/Ops/角色/通知/ApiDocs/资料均有 `PageAsyncState` 与 `loadError` |

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `frontend/tests/unit/remainingPages.test.mjs` | 新建源码断言 |
| `frontend/src/views/TaskDetail.vue` | 结果分页、失败旗标、PageAsyncState |
| `frontend/src/views/DatasetDetail.vue` | loadError、样本 pager 常显 |
| `frontend/src/views/Dashboard.vue` | 异常任务成功空表改 EmptyState |
| `frontend/src/views/Leaderboard.vue` | 去掉独立 obs 皮肤，统一页头/卡片/表格 |
| `frontend/src/views/TaskTemplates.vue` | EmptyState + loadError + PageAsyncState |
| `frontend/src/views/Benchmarks.vue` | 列表失败/空态 |
| `frontend/src/views/Safety.vue` | 列表失败/空态 |
| `frontend/src/views/Ops.vue` | status/backup 区域失败旗标 |
| `frontend/src/views/RolePermission.vue` | catch 写 loadError，不再静默 `roles=[]` |
| `frontend/src/views/NotificationManage.vue` | 列表 catch + PageAsyncState |
| `frontend/src/views/ApiDocs.vue` | OpenAPI 失败展示错误与下一步 |
| `frontend/src/views/Profile.vue` | getMe 失败旗标 |
| `frontend/src/views/Login.vue` | 表单 `displayMsg` |
| `frontend/src/views/AuditLog.vue` | 禁用导出按钮 |
| `frontend/src/views/Users.vue` | 禁用/启用 + creatorOptionsError |

未新增权限码。未创建 commit。未开始 Task 6。

## 行为摘要

- 详情与其余页统一 `deriveAsyncState` + `PageAsyncState`；成功空列表用 EmptyState；失败不伪装成 0 条。
- TaskDetail 结果请求带 `page`/`page_size`/`total`，成功后 pager 常显。
- DatasetDetail 样本 pager 不再用 `itemTotal > itemPageSize` 隐藏。
- Leaderboard 使用产品页头与 Element 组件；cohort/冻结尺度作为操作元数据保留，不再用铜光观测台作为页面身份。
- AuditLog 导出按钮 `disabled`，提示「当前环境未开放导出」。
- Users 在 `user:edit` 下确认后 `status: 'disabled'` / 启用 `active`；`creatorOptions` catch 写 `creatorOptionsError`。
- Login 校验失败与接口失败都写 `displayMsg`；提交仍受 `loading` 锁定。
- ApiDocs 探测 `/openapi.json` 失败时展示错误，并提示刷新或新窗口打开 `/docs`。

## 自审

- [x] TDD：先测后码；RED 为 7 条 `remainingPages` 失败。
- [x] `npm run test:unit` 65/65。
- [x] `verify:ux-static` OK。
- [x] 未 git commit。
- [x] 未开始 Task 6。
