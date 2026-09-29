# Task D3 报告：403 与口号

## 状态

**DONE** — `frontend` `npm run test:unit` **53/53 pass**；`npm run verify:ux-static` **OK**；未 commit。未启动 Task 4。未做浏览器端到端验证（本环境未对改动页做交互抽检）。

## RED

**命令：**

```powershell
cd E:\eval-platform\frontend
npm run test:unit
```

**关键输出：**

```
# tests 52
# pass 48
# fail 4
```

**失败原因：** `forbiddenNav.test.mjs` 已要求 `/not-found` + `reason: 'forbidden'`、Agents 新 page-desc、去掉 `plannerModels.value[0]`、Models 新 hint、verify-ux-static 以 `无法探测或试调用` 为 error 条件；当时源码仍是旧导航与口号（TDD 预期 RED）。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\frontend
npm run test:unit
npm run verify:ux-static
```

**结果：** `tests 53` — **pass 53 / fail 0**；`[verify:ux-static] OK`（`routes sampled=20 nav=13 warnings=0`）。

| 用例 | 说明 |
| --- | --- |
| `router sends unauthorized visits to /not-found…` | 无权限走 `/not-found`，query `reason=forbidden` + `from`；不再写 `denied` |
| `Agents does not auto-select first planner model…` | 无 `plannerModels.value[0]`；page-desc / 试用开关新文案；placeholder 必选；生成计划依赖规划模型 |
| `Models hint forbids Mock fallback wording` | 精确 hint；无 Mock 回退句 |
| `NotFound treats reason=forbidden as 403…` | 403 文案；兼容 `denied`；`from` 文本插值、无 v-html |
| `verify-ux-static requires probe hint…` | 强制 `无法探测或试调用`；不再把「不会回退到本地 Mock」当通过条件 |

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `frontend/src/router/index.js` | 无权限 `next({ path: '/not-found', query: { reason: 'forbidden', from } })`；显式 `/not-found` 路由；登录回跳仍用 `safeHomePath` |
| `frontend/src/views/NotFound.vue` | `reason=forbidden` 或旧 `denied` 显示 403；`from` 纯文本展示 |
| `frontend/src/views/Agents.vue` | 新 page-desc；试用开关文案；去掉自动选第一项；生成计划未选模型 disabled；`createSession` 无模型直接 return |
| `frontend/src/views/Models.vue` | field-hint 改为 `未配置 api_url 时无法探测或试调用。` |
| `frontend/scripts/verify-ux-static.mjs` | 仍 error `留空则使用本地 Mock`；缺 `无法探测或试调用` 为 error |
| `frontend/tests/unit/forbiddenNav.test.mjs` | 新建源码断言 |

Dashboard 的 `route.query.denied` banner 未删（兼容旧链）。未创建 commit。

## 行为摘要

- 已登录但缺少 `to.meta.permission`：一律 403 页，不再 `firstAccessiblePath` + `denied`，无 dashboard 特例。
- 未登录仍 `/login?redirect=`；已登录访问 `/login` 仍 `safeHomePath`。
- 规划模型无默认选中；「生成计划」未选则 disabled，且 `createSession` 不静默用第一项。
- Models / Agents 去掉 Mock 口号；静态门禁用新探测文案做硬失败。

## 自审

- [x] TDD：先测后码；RED 为 4 条 forbiddenNav 失败。
- [x] `npm run test:unit` 53/53。
- [x] `verify:ux-static` OK。
- [x] 未 git commit。
- [x] 未开始 Task 4。
