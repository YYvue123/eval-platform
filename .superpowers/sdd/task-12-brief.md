# Task 12：向导支持 HTTP 工具、两步 Skill、Streamable HTTP 与 stdio MCP

Work from E:\eval-platform. Do not git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>". Keep Task 11 trial panel. Do not implement Task 13 five-phase MCP workbench (stdio in the *wizard* is this task; the MCP connection dialog five-state bar is Task 13).

stdioAliases GET /resources/mcp/stdio-aliases exists with resource:create.

Skill tool picker must use server list pagination; user must not type arbitrary resource_id.

s2 binding example uses s1.output.values; parse HTTP tools return values via Skill _step_result adapter on the backend.

Extract wizard helpers to a unit-tested module if Resources.vue is too large, but keep UX in Resources.vue.

## Global constraints

- 不创建 commit
- collect-permissions / verify:ux-static / build
- no new permission actions unless required
- 产品文案不写研发口号

## Plan text

## Task 12：向导支持 HTTP 工具、两步 Skill、Streamable HTTP 与 stdio MCP

**Files:**
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/views/Resources.vue`

**Interfaces:**
- `resourcesApi.stdioAliases()`

- [ ] **Step 1：增加 stdio aliases API**

```javascript
stdioAliases: () => request.get('/resources/mcp/stdio-aliases'),
```

- [ ] **Step 2：扩展向导模型**

`emptyWizard()` 增加：

```javascript
mcpTransport: 'streamable_http',
commandAlias: '',
skillSteps: [
  { step_id: 's1', resource_id: '', inputJson: '{}' },
  { step_id: 's2', resource_id: '', inputJson: '{}' },
],
```

Skill 步骤不再只有一个 `input_ref` 字符串；每步使用 JSON 输入绑定编辑器，例子：

```json
{"text":{"$ref":"$input.text"}}
```

和：

```json
{"values":{"$ref":"s1.output.values"},"target_unit":{"$ref":"$input.target_unit"}}
```

每个步骤解析失败时保留原文，并显示具体步骤错误。

- [ ] **Step 3：Skill 工具改为远程选择器**

进入 Skill 配置时调用：

```javascript
resourcesApi.list({
  resource_type: 'tool',
  status: 'online',
  page: 1,
  page_size: 50,
  search,
})
```

选择器显示 name/resource_id/version/health；滚动或搜索继续服务端分页。禁止自由输入不可见 resource_id。

- [ ] **Step 4：MCP 传输分支**

选择 Streamable HTTP 时显示 endpoint、credential_ref、egress allowlist。

选择 stdio 时：
- 调用 `stdioAliases()`；
- 只显示 alias 下拉；
- 无 alias 时显示“服务端未配置允许的 stdio 服务，请联系管理员配置”；
- 不显示任意命令输入框。

Manifest：

```javascript
const interfaces = wizard.value.mcpTransport === 'stdio'
  ? { transport: 'stdio', command_alias: wizard.value.commandAlias }
  : {
      transport: 'streamable_http',
      endpoint: wizard.value.endpoint,
      method: 'POST',
      auth_type: wizard.value.credentialRef ? 'bearer' : 'none',
    }
```

- [ ] **Step 5：完整向导校验**

`nextWizard()`：
- HTTP 工具 endpoint 必须 http(s)；
- MCP Streamable HTTP endpoint 必须 http(s)；
- MCP stdio alias 必须来自服务端列表；
- Skill 至少 1 步，每步必须选择工具，step_id 唯一，inputJson 必须解析为对象；
- 改 transport/endpoint/alias/步骤/schema/credential_ref 均调用 `invalidateChecks()`。

`runWizardChecks()`：
- MCP 用对应 transport probe；
- Tool 只做结构检查，不把未执行显示为成功；
- Skill 校验所有引用，最终真实试用在注册后进行。

- [ ] **Step 6：修复 Schema 来回转换的有损逻辑**

删除 `pullSchemaFromJson()` 中 `integer → number` 转换。字段表只能编辑受支持的简单字段；若 JSON 含 enum/description/nested/range，显示“高级 Schema 已保留，字段表不支持无损编辑”，禁止自动覆盖原 JSON。

- [ ] **Step 7：权限与构建检查**

当前按钮继续使用：

```vue
v-if="userStore.hasPermission('resource:create')"
v-if="userStore.hasPermission('resource:invoke')"
```

Run:

```powershell
npm run collect-permissions
npm run verify:ux-static
npm run build
```

Expected: PASS；`permissions.json` 无意外新增动作。

- [ ] **Step 8：记录文件清单**

记录 Task 12 全部文件及权限收集差异。

