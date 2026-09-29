# Task D2 报告：listQuery 与 request 静默

## 状态

**DONE** — `frontend` `npm run test:unit` **48/48 pass**；`npm run verify:ux-static` **OK**；未 commit。未启动 Task 3。未做浏览器端到端验证（本环境无运行中的前端服务）。

## RED

**命令：**

```powershell
cd E:\eval-platform\frontend
npm run test:unit
```

**关键输出：**

```
Error [ERR_MODULE_NOT_FOUND]: Cannot find module 'E:\\eval-platform\\frontend\\src\\utils\\listQuery.js'
# tests 40
# pass 39
# fail 1
```

**失败原因：** `listQuery.test.mjs` 已引用 `readListQuery` / `writeListQuery`，模块尚未创建（TDD 预期 RED）。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\frontend
npm run test:unit
npm run verify:ux-static
```

**结果：** `tests 48` — **pass 48 / fail 0**；`[verify:ux-static] OK`（`routes sampled=20 nav=13 warnings=0`）。

| 用例 | 说明 |
| --- | --- |
| `missing query → page 1, page_size 20…` | 缺省 query 归一化 |
| `page=0 or NaN → 1` | 页码下限 |
| `page_size=500 → 100` | 页大小上限 |
| `writeListQuery merges and drops empty keys` | 假 router：合并、删空、`replace` |
| `request interceptor honors skipErrorToast…` | 源码断言双路径 config + 仍 `reject` |
| `unread-count polling sets skipErrorToast` | `getUnreadCount` 带旗标 |
| `Dashboard load failure sets loadError…` | 失败不伪装空待办 |
| `Agents loadList sets error flags…` | 去掉 `catch(() => ({ items: [] }))` |
| `NotificationManage loadUsers sets usersLoadError` | 受众选择旁展示错误 |

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `frontend/src/utils/listQuery.js` | 新建：`readListQuery` / `writeListQuery`；页眉注明 catch 不得无 error 地 `items=[]` |
| `frontend/src/utils/request.js` | `skipErrorToast`（`error.config` 与 `error.response.config`）；401 仍登出跳转（auth 端点除外）；始终 `reject` |
| `frontend/src/api/index.js` | `getUnreadCount` 传 `{ skipErrorToast: true }` |
| `frontend/src/views/Dashboard.vue` | `loadError` + `PageAsyncState` error；失败不再把 workbench 写成空成功 |
| `frontend/src/views/Agents.vue` | `modelsLoadError` / `sessionsLoadError`；模型下拉与会话栏展示错误 |
| `frontend/src/views/NotificationManage.vue` | `usersLoadError` 展示在「发送给」选择旁 |
| `frontend/tests/unit/listQuery.test.mjs` | 新建：listQuery 行为 + 静默/失败态源码断言 |

未改 `fetchList` 静默清空（简报仅要求 unread-count 轮询）。未改规划模型 `items[0]` 默认（留给 Task 3）。未创建 commit。

## 行为摘要

- `readListQuery`：page≥1；page_size 缺省 20、上限 100；`q`/`status` 非字符串视为 `''`。
- `writeListQuery`：合并当前 query，空/`null` 键删除，其余转字符串后 `router.replace`。
- 拦截器：`skipErrorToast` 压掉所有 `ElMessage.error`（含 auth 401 与无 response 网络错误）；非 auth 401 仍 logout + `/login`。
- 工作台失败：只设 `loadError`，不渲染「暂无待办」。
- 评测助手：会话失败不再显示「暂无会话」；模型列表失败在规划模型选择旁显示错误，同时 `plannerModels=[]`。

## 自审

- [x] TDD：先测后码；RED 为 `ERR_MODULE_NOT_FOUND`。
- [x] `npm run test:unit` 48/48。
- [x] `verify:ux-static` OK。
- [x] 未 git commit。
- [x] 未开始 Task 3。

## 关注点

1. **request 单测为源码断言：** 未 mount Axios 拦截器；行为靠 `skipToast` 分支与双 config 检查。
2. **Dashboard 部分失败：** `getStats` 成功后 `getWorkbench` 失败仍整页 error（不拆分卡片失败，留给后续 D 任务）。
3. **无浏览器验证：** 失败 UI 依赖运行中的前后端；本任务以单元测试与静态 UX 校验为准。
