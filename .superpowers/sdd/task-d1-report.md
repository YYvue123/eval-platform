# Task D1 报告：六态纯函数 + PageAsyncState

## 状态

**DONE** — `frontend` `npm run test:unit` **39/39 pass**；`npm run verify:ux-static` **OK**；未 commit。组件尚未挂到业务页，未做浏览器端到端验证。

## RED

**命令：**

```powershell
cd E:\eval-platform\frontend
npm run test:unit
```

**关键输出：**

```
Error [ERR_MODULE_NOT_FOUND]: Cannot find module 'E:\\eval-platform\\frontend\\src\\utils\\asyncState.js'
# tests 35
# pass 34
# fail 1
```

**失败原因：** 测试已引用 `deriveAsyncState` / `ASYNC_STATE_COPY` 与 `PageAsyncState.vue`，模块与组件尚未创建（TDD 预期 RED）。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\frontend
npm run test:unit
npm run verify:ux-static
```

**结果：** `tests 39` — **pass 39 / fail 0**；`[verify:ux-static] OK`（`routes sampled=20 nav=13 warnings=0`）。

| 用例 | 说明 |
| --- | --- |
| `deriveAsyncState covers all six branches` | loading / error / forbidden / empty / uncreated / success |
| `forbidden wins over loading` | forbidden 优先于 loading 与 error |
| `createdOnce empty vs uncreated` | 空列表：`createdOnce`→empty，否则 uncreated |
| `ASYNC_STATE_COPY has title and next…` | 六态均有标题；无 Mock 口号 |
| `PageAsyncState shows badge plus copy…` | StatusBadge phase 映射 + 默认 slot；非纯颜色 |

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `frontend/src/utils/asyncState.js` | 新建：`deriveAsyncState`、`ASYNC_STATE_COPY` |
| `frontend/src/components/PageAsyncState.vue` | 新建：非 success 显示徽章+标题+下一步（及可选 `errorMessage`）；success 默认 slot |
| `frontend/tests/unit/asyncState.test.mjs` | 新建：六分支 + 优先级 + 空态区分 + 组件静态断言 |
| `.superpowers/sdd/progress.md` | Task 1 complete |

未改动简报外业务页；未创建 commit。

## 行为摘要

- 优先级：`forbidden` → `loading` → `error` → 空列表（`createdOnce` 则 `empty`，否则 `uncreated`）→ `success`。
- `items`：数组按长度；`null`/`undefined` 视为空；其它值包成单元素。
- 徽章：loading→running，error→failed，forbidden→blocked，empty/uncreated→idle。
- 错误态同时展示固定「下一步」文案与 `errorMessage`（若有）。

## 自审

- [x] TDD：先测后码；RED 为 `ERR_MODULE_NOT_FOUND`。
- [x] `npm run test:unit` 39/39。
- [x] `verify:ux-static` OK。
- [x] 无 Mock 口号。
- [x] 未 git commit。

## 关注点

1. **未接入页面：** 后续 D 任务才会把 `PageAsyncState` 挂到各列表/详情。
2. **单测未 mount Vue：** 组件行为用 SFC 源码断言（与现有 `node --test` 一致），无组件渲染测试。
3. **success 的 `next` 为空：** 该态走 slot，不展示空下一步。
