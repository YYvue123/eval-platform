# Task 13 实施报告：MCP 五态工作台与错误恢复

## Status

完成。MCP 工作台改为单一 `mcpState` 五步条（未配置/结构有效/已协商/已发现/最近调用），映射 probe 的 `ok`、`session`、`error.code`、`notifications` 与详情 `mcp_catalog.stale`。HTTP 200 且 `ok=false` 不弹成功。向导（Task 12）与试用历史（Task 11）保留。未创建 commit。

## TDD 记录

### RED

`Cannot find module '...\\src\\utils\\mcpWorkbench.js'`（`tests/unit/mcpWorkbench.test.mjs`）。

### GREEN

```text
npm run test:unit          # tests 29, pass 29, fail 0
npm run verify:ux-static   # OK, routes sampled=20, warnings=0
npm run build              # ✓ 2298 modules, built in 20.79s
```

权限采集仍为 55 个码，无新动作。

## What you implemented

- 单一状态机：来源完整→configured；initialize 成功写入 protocol_version/server_info；list 成功才 listed；call 的 `ok=false`→`lastCall=failed`；任一步失败清空后续绿态。
- 五步条：图标 + StatusBadge 文本；stale 显示「目录已变化，请重新获取」，成功 list 前不清除。
- 工具搜索；错误区 code/message/`MCP_RECOVERY`；调用前 SchemaForm.validate；已注册走 `resource_id` 与 Task 11 风格调用历史；临时地址提示租户探测记录不属于已注册资源。
- 对话框 `min(920px, calc(100vw - 24px))`；窄屏表格横滚、参数与结果上下排列。

## Files

- Create: `frontend/src/utils/mcpWorkbench.js`
- Create: `frontend/tests/unit/mcpWorkbench.test.mjs`
- Modify: `frontend/src/views/Resources.vue`
- Modify: `frontend/src/components/StatusBadge.vue`
- Create: `.superpowers/sdd/task-13-report.md`

## Concerns

- 未做浏览器点通；窄屏/footer 依赖 CSS 与 Element Plus 对话框滚动。
- 已注册 MCP 的 session 字段依赖 invoke metadata 中的 `mcp_session`。

## Review fix（stale 跨资源继承）

切换 MCP 来源时不再继承上一个资源的 `stale`。`sourceKey(mode, form)` 比较 resource_id / endpoint / mode；身份变化时从 `emptyMcpState` 起步，只采用新的 `catalogStale`。同一来源仍为 `prev.stale || catalogStale`，直到本次会话成功 `tools/list`。`Resources.vue` 的 probe 来源 watch 改为 `emptyMcpState()`，不再 `{ ...empty, stale: prev.stale }`。

TDD：先补失败用例（identity 变化仍 `true !== false`），再改实现。

```text
npm run test:unit          # tests 33, pass 33, fail 0
npm run verify:ux-static   # OK, routes sampled=20, warnings=0
```

未创建 commit。
