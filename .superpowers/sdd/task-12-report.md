# Task 12 实施报告：向导支持 HTTP 工具、两步 Skill、Streamable HTTP 与 stdio MCP

## Status

完成。注册向导支持 HTTP 工具、两步 Skill JSON `$ref` 绑定、MCP Streamable HTTP 与
stdio 别名下拉。试用台调用历史 UI 未改。未实现 Task 13 五态 MCP 工作台，未创建 commit。

## TDD 记录

### RED

命令：`cd E:\eval-platform\frontend && npm run test:unit`

```text
Error [ERR_MODULE_NOT_FOUND]: Cannot find module
'E:\\eval-platform\\frontend\\src\\utils\\resourceWizard.js'
not ok 2 - tests\\unit\\resourceWizard.test.mjs
# tests 12
# pass 11
# fail 1
```

失败原因符合预期：助手模块尚不存在。

### GREEN

```text
npm run test:unit     # tests 20, pass 20, fail 0
npm run collect-permissions  # 55 个权限码
npm run verify:ux-static     # OK, routes sampled=20, warnings=0
npm run build                # ✓ 2297 modules transformed, built in 17.75s
```

`permissions.json` / `permissions.discovered.json` 相对当前工作区无新增动作。

## What you implemented

- `resourcesApi.stdioAliases()` → `GET /resources/mcp/stdio-aliases`（`resource:create`）。
- Skill：服务端分页远程选择器（name/resource_id/version/health），禁止自由输入 resource_id；
  每步 `inputJson` 对象绑定，默认 s1 `$input.text`、s2 `s1.output.values`；解析失败保留原文。
- MCP：Streamable HTTP 显示 endpoint/凭证/egress；stdio 仅 alias 下拉，无 alias 提示联系管理员。
- 校验：HTTP(s) endpoint、stdio alias 必须在服务端列表、Skill 工具/唯一 step_id/对象 JSON；
  MCP probe 按 transport；Tool/Skill 不把未执行标为成功。
- Schema：删除 integer→number；含 enum/description/nested/range 时提示并禁止字段表覆盖 JSON。

## Files

- Create: `frontend/src/utils/resourceWizard.js`
- Create: `frontend/tests/unit/resourceWizard.test.mjs`
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/views/Resources.vue`
- Create: `.superpowers/sdd/task-12-report.md`

## Concerns

- 向导需登录后才能在浏览器点通；本次以单测 + 静态门禁 + production build 验证。
- Skill 选择器滚动分页依赖 Element Plus 下拉 `scroll` 绑定；搜索会重置页码但保留已选项。
- HTTP 工具列表结果到 `s1.output.values` 的适配仍由后端 `_step_result` 负责。
