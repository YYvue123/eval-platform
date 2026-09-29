# 子项目 D 验收证据（全站 24 页六态）

日期：2026-09-29。工作目录：`E:\eval-platform`。**未提交**。前端单测不访问 `backend/eval_platform.db`（N/A）。

本文件只记录本次 Task 6 实测。六态矩阵以**源码**为准。浏览器只对已截图页面的**当时可见态**计 visual；未截图的态不标 browser pass。

## 命令结果

工作目录：`E:\eval-platform\frontend`。

### `npm run test:unit`

```text
# tests 65
# suites 0
# pass 65
# fail 0
# cancelled 0
# skipped 0
# todo 0
# duration_ms 247.8932
```

退出码 0。

### `npm run verify:ux-static`

```text
[collect-permissions] 发现 55 个权限码，已写入 permissions.discovered.json
[verify:ux-static] OK
  routes sampled=20 nav=13 warnings=0
```

退出码 0。

### `npm run build`

```text
vite v5.4.21 building for production...
✓ 2303 modules transformed.
✓ built in 28.79s
```

退出码 0。`prebuild` 同样写出 55 个权限码。

## 截图

探测：`GET http://127.0.0.1:5173/login` → 200；`GET http://127.0.0.1:8000/api/live` → 200 `{"ok":true,...}`。`4173`（Vite preview）未监听，未用 preview。`8001` 未监听。

对 **已运行** 的 Vite `http://127.0.0.1:5173` 用 Playwright Chromium 截视口（非全页）。登录使用本机开发默认账号（口令不写入本文件）。认证后页面未 blocked。

路径：`docs/superpowers/evidence/d-screenshots/`。

| 文件 | 视口 | 当时可见态（不得外推为六态全过） |
| --- | --- | --- |
| `login-1440.png` `login-1024.png` `login-390.png` | 1440 / 1024 / 390 | 登录表单 idle |
| `resources-1440.png` `resources-1024.png` `resources-390.png` | 同上 | 工具中心列表 **success**（有行）；390 侧栏与主栏重叠 |
| `agents-1440.png` `agents-1024.png` `agents-390.png` | 同上 | 评测助手 **success**（侧栏有会话） |
| `tasks-1440.png` `tasks-1024.png` `tasks-390.png` | 同上 | 任务列表 **empty**（EmptyState「暂无任务」+ pager 共 0 条） |

未拍：loading / error / forbidden / uncreated。这四态 **没有** browser 证据。

## 24 页六态矩阵

路由视图 24 个（`Login` + MainLayout 22 子路由 + `NotFound`；catch-all 同 `NotFound.vue`）。

图例：

| 标记 | 含义 |
| --- | --- |
| PAS | `PageAsyncState` + `deriveAsyncState`（或等价 `state=` + `loadError`） |
| ES | 成功空列表走 `EmptyState` |
| LE | catch 写 `loadError` / 专用错误旗标，不把失败伪装成无错误空数组 |
| R | `meta.permission` 失败 → `/not-found?reason=forbidden`（页内 `forbidden: false` 仍算 **仅路由**） |
| P | 部分：按钮 loading、表单错误、自定义文案、`v-loading` |
| G | 缺口 |
| — | 该页语义上不适用 |

**Browser** 列只填本轮截图实际看到的态；其余为「无截图」。

| 页 | loading | error | forbidden | empty | uncreated | success | Browser |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Login | P（按钮 `:loading`） | P（`displayMsg`，非 PAS） | —（public） | — | — | 表单 | idle 三宽 |
| Dashboard | G（无 loading 旗标/PAS） | PAS+LE | R + 遗留 `?denied` 横幅 | ES（分区） | G（空与未创建未分） | 卡片/表 | 无截图 |
| NotificationManage | PAS | PAS+LE；受众 `usersLoadError` | R（页内 `forbidden: false`） | ES | PAS | 表+pager | 无截图 |
| RolePermission | PAS | PAS+LE | R（页内 false） | ES | PAS | 角色表 | 无截图 |
| Profile | PAS | PAS+LE | —（无 route permission） | —（对象页） | PAS（无 id 且未 createdOnce） | 表单 | 无截图 |
| Users | PAS | PAS+LE | PAS+R（403 置 `forbidden`） | ES | PAS | 表+pager | 无截图 |
| AuditLog | PAS | PAS+LE | PAS+R | ES | PAS | 表+pager；导出 disabled | 无截图 |
| Ops | PAS | PAS+LE | R（页内 false） | ES（准入空） | PAS | 面板 | 无截图 |
| ApiDocs | G | PAS+LE（仅失败才 PAS） | — | — | G | Swagger 容器 | 无截图 |
| Datasets | PAS | PAS+LE | PAS+R | ES | PAS | 表+URL pager | 无截图 |
| DatasetDetail | PAS | PAS+LE | R（页内 false） | G（样本表无 EmptyState） | PAS（无详情对象） | 详情+样本 pager | 无截图 |
| Quality 报告/工单 | PAS | PAS+LE | PAS+R | ES | PAS | 表+URL pager | 无截图 |
| Quality 规则 | G | G（`loadRules` 无 catch） | R | G | G | 整表一次拉齐 | 无截图 |
| Models | P（`v-loading`） | G（`loadData` 无 catch/`loadError`） | R | ES | G | 表；pager `total>0` 才显 | 无截图 |
| Prompts | PAS | PAS+LE | PAS+R | ES | PAS | 表+URL pager | 无截图 |
| Resources | P（`v-loading`） | G（列表 `loadData` 无 `loadError`） | R | G（无 EmptyState/`#empty`） | G | 表+pager | success 三宽 |
| Tasks | PAS | PAS+LE | PAS+R | ES | PAS | 表+URL pager | **empty** 三宽 |
| TaskTemplates | PAS | PAS+LE | R | ES | PAS | 目录表 | 无截图 |
| Benchmarks | PAS | PAS+LE | R | ES | PAS | 表 | 无截图 |
| Safety | PAS | PAS+LE | R | ES | PAS | 类别表 | 无截图 |
| TaskDetail | PAS | PAS+LE | R | G（结果空无专用 EmptyState） | PAS | 详情+结果 pager | 无截图 |
| Leaderboard | PAS | PAS+LE | R | ES | PAS | 表 | 无截图 |
| EvalServices | PAS | PAS+LE | PAS+R | ES | PAS | 表+URL pager；看板 `Promise.all` 耦合 | 无截图 |
| Agents | P | P（`sessionsLoadError`/`modelsLoadError`，非 PAS） | R | P（「暂无会话」） | P（无 `currentId` 的起步卡） | 工作台 | success 三宽 |
| NotFound | — | — | 403 文案（`reason=forbidden`） | — | — | 404 文案 | 无截图 |

## 已知缺口（诚实保留）

- **Quality 检测规则**：`GET` 规则数组、无 `page`/`total`；表不分页；加载失败无 `loadError`。
- **Models / Resources 列表**：未接 PAS；Resources 列表失败可保持旧 `items` 且无页级错误；Models 失败同样无旗标。
- **Agents**：六态用自定义侧栏/起步卡，不是 `PageAsyncState`。
- **Dashboard**：无 loading PAS；`?denied` 横幅仍在（主路径已是 NotFound）。
- **EvalServices**：列表与看板/工作空间 `Promise.all`，一失败则整页 error。
- **详情空样本/空结果**：DatasetDetail / TaskDetail 成功后空表不一定 EmptyState。
- **页内 forbidden**：多数页 `forbidden: false`，依赖路由守卫；页面已打开后的 403 不走 PAS forbidden。
- **C live fill**：隔离栈 `8001` 未跑；活动库 REAL01/02/04/05 不得标 pass（见 `subproject-c.md`）。缺 `L3_MODEL_API_URL` 的 REAL03/06/07/08、REAL10/11 仍 blocked。
- **B apply busy**：活动库未 apply；隔离拷贝首次 apply 因 `running/queued` 拒绝，仅在副本 pause 后闭环（见 `subproject-b.md`）。
- **390 Resources**：侧栏打开时主栏被压住，按钮文字截断。
- **单测形态**：多为 SFC 源码正则，无 Vue mount、无六态 E2E。
- **Audit 导出**：按钮 disabled +「当前环境未开放导出」，无真实导出 API。

未把 Mock / 未测项标为正式 pass。
