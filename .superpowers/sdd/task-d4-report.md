# Task D4 报告：列表页分页与 URL

## 状态

**DONE** — `frontend` `npm run test:unit` **58/58 pass**；`npm run verify:ux-static` **OK**；未 commit。未启动 Task 5。未做浏览器端到端交互抽检（验证按简报为单测 + 静态 UX 门）。

## RED

**命令：**

```powershell
cd E:\eval-platform\frontend
npm run test:unit
```

**关键输出：**

```
# tests 58
# pass 53
# fail 5
```

**失败原因：** `listPages.test.mjs` 已要求去掉 `v-if="total > pageSize"`、Quality/Prompts/EvalServices 不得只拉 `page_size: 50`、七页接入 `readListQuery`/`writeListQuery`、ResourcePicker 加载更多、Users catch 写 `loadError`；当时源码仍是旧列表行为（TDD 预期 RED）。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\frontend
npm run test:unit
npm run verify:ux-static
```

**结果：** `tests 58` — **pass 58 / fail 0**；`[verify:ux-static] OK`（`routes sampled=20 nav=13 warnings=0`）。

| 用例 | 说明 |
| --- | --- |
| `Datasets.vue and Users.vue do not hide pager…` | 去掉 `total > pageSize` 隐藏分页 |
| `Quality/Prompts/EvalServices page with page+page_size…` | 列表请求带 `page`/`page_size` 并读 `total` |
| `seven list views sync URL…` | 七页均有 `readListQuery` 或 `writeListQuery` |
| `ResourcePicker pages beyond first 30…` | `__more__` / 加载更多 + `loadError` |
| `Users.vue catch sets loadError…` | catch 不再 `items=[]` 且无错误旗标 |

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `frontend/tests/unit/listPages.test.mjs` | 新建源码断言 |
| `frontend/src/views/Datasets.vue` | URL 分页筛选、常显 pager、`PageAsyncState`、失败不空表 |
| `frontend/src/views/Tasks.vue` | 同上；`total===0` 仍显示分页行；轮询静默刷新 |
| `frontend/src/views/Quality.vue` | 报告/工单分页+URL+EmptyState；规则表未分页 |
| `frontend/src/views/Prompts.vue` | `list({ page, page_size, search })` + total + pager + URL |
| `frontend/src/views/EvalServices.vue` | `list({ page, page_size })` + total + pager + URL；看板/工作空间仍独立请求 |
| `frontend/src/views/Users.vue` | URL 同步、常显 pager、catch 写 `loadError` |
| `frontend/src/views/AuditLog.vue` | URL 同步、`PageAsyncState`、失败旗标 |
| `frontend/src/components/ResourcePicker.vue` | 分页游标 + 加载更多追加；检索失败展示 `loadError` |

未改无关详情弹窗（如 Prompts 详情里数据集/模型 `page_size: 50`）。未创建 commit。

## 行为摘要

- 七个列表页：`readListQuery(route.query)` 初始化 `page/page_size/q/status`；加载与翻页/筛选时 `writeListQuery`；监听 `route.query` 恢复后退状态。
- loading/error/forbidden/uncreated → `PageAsyncState`；empty/success → 表格（`#empty` 可用 EmptyState）；有 `loadError` 不走空表伪装。
- `createdOnce` 仅在成功响应后置 true；catch 设错误旗标，不清成无错误的空数组。
- Quality **检测规则** 表保持不分页：后端 `GET /quality/rules` 返回规则数组、无 `page`/`total`。
- ResourcePicker：`search()` 重置 `page=1` 替换选项；`total > options.length` 或本页条数等于 `page_size` 时出现「加载更多」；选 `__more__` 不改 v-model，请求下一页并去重追加。hydrate 当前值失败可忽略；列表检索失败必须 `loadError`。

## 自审

- [x] TDD：先测后码；RED 为 5 条 `listPages` 失败。
- [x] `npm run test:unit` 58/58。
- [x] `verify:ux-static` OK。
- [x] 未 git commit。
- [x] 未开始 Task 5。
