# Task 13：MCP 五态工作台与错误恢复

Work from E:\eval-platform. Do not git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>". Keep Task 11/12 wizard and trial panel.

Probe API now returns ok, session.protocol_version, session.server_info, error.code, notifications, and mcp_catalog.stale on resource detail. Map those into mcpState. Probe of registered resources uses resource_id; do not treat HTTP 200 with ok=false as success toast.

Extract MCP_RECOVERY and phase transitions to a unit-tested helper if possible.

## Global constraints

- 不能只用颜色表达状态
- 请求失败不能伪装成功
- 不创建 commit
- npm test:unit, verify:ux-static, build

## Plan text

## Task 13：MCP 五态工作台与错误恢复

**Files:**
- Modify: `frontend/src/views/Resources.vue`
- Modify: `frontend/src/components/StatusBadge.vue`

- [ ] **Step 1：定义单一工作台状态**

替换三个布尔值：

```javascript
const mcpState = ref({
  phase: 'unconfigured',
  schemaValid: false,
  negotiated: false,
  listed: false,
  lastCall: 'not_run',
  stale: false,
  protocolVersion: '',
  serverName: '',
  toolCount: 0,
  error: null,
})
```

状态转换：
- 来源完整 → `configured`；
- initialize 成功 → `negotiated`；
- tools/list 成功 → `listed`；
- tools/call → `success` 或 `failed`；
- 任一步失败，后续状态清空，不能沿用绿色。

- [ ] **Step 2：五步状态条**

展示：
1. 未配置/已配置；
2. 结构有效；
3. 已协商（协议版本、服务器名）；
4. 已发现 N 个工具（stale 时 warning）；
5. 最近调用成功/失败/未执行。

不能只用颜色表达；每一步有文本与图标。

- [ ] **Step 3：工具目录搜索与 stale**

```javascript
const mcpToolSearch = ref('')
const filteredMcpTools = computed(() => {
  const term = mcpToolSearch.value.trim().toLowerCase()
  if (!term) return mcpTools.value
  return mcpTools.value.filter((tool) =>
    `${tool.name} ${tool.description || ''}`.toLowerCase().includes(term)
  )
})
```

收到 `notifications/tools/list_changed` 或 detail 的 `mcp_catalog.stale` 后显示“目录已变化，请重新获取”；重新获取成功前不得清除 stale。

- [ ] **Step 4：稳定错误码映射恢复动作**

```javascript
const MCP_RECOVERY = {
  MCP_AUTH_FAILED: '检查凭证引用是否存在且当前服务可读取。',
  MCP_TIMEOUT: '确认服务已启动、地址可访问，并检查超时设置。',
  MCP_SESSION_EXPIRED: '会话已过期，请重新验证连接。',
  MCP_TOOL_ERROR: '连接正常，但工具拒绝了输入；请按 inputSchema 修正参数。',
  MCP_STDIO_NOT_ALLOWED: '该 stdio 别名未获服务端允许。',
  MCP_TRANSPORT_ERROR: '连接中断，请检查传输方式与服务日志。',
  MCP_PROTOCOL_ERROR: '服务返回协议错误，请核对 MCP 版本与方法。',
}
```

错误区显示 code、message、恢复指引；不能 catch 后只显示 `String(error)`。

- [ ] **Step 5：SchemaForm 校验 MCP 参数**

给 MCP 参数表单加 ref。调用前：

```javascript
const validation = mcpSchemaRef.value?.validate()
if (validation && !validation.ok) {
  const [field, message] = Object.entries(validation.errors)[0]
  ElMessage.error(`${field}：${message}`)
  return
}
```

调用返回 `ok=false` 时必须 `mcpState.lastCall='failed'`，不能弹 success。

- [ ] **Step 6：最近调用和响应式**

注册资源模式下显示 Task 11 的调用历史；临时地址模式明确写“临时探测记录仅按当前租户保存，不属于已注册资源”。

对话框宽度改为 `min(920px, calc(100vw - 24px))`；390px 下表格横滚、参数表单与结果上下排列、footer 不遮挡内容。

- [ ] **Step 7：构建验证**

Run:

```powershell
npm run test:unit
npm run verify:ux-static
npm run build
```

Expected: PASS。

- [ ] **Step 8：记录文件清单**

记录 Task 13 全部文件。

