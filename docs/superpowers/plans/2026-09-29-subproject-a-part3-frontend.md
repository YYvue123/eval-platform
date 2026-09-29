# 子项目 A 实施计划（3/3）：前端与验收

> 先读总计划、part1、part2。Task 10 可与 Task 7–9 独立执行；Task 11–13 依赖对应后端接口。

## Task 10：无损 SchemaForm

**Files:**
- Create: `frontend/src/utils/schemaForm.js`
- Create: `frontend/tests/unit/schemaForm.test.mjs`
- Modify: `frontend/src/components/SchemaForm.vue`
- Modify: `frontend/package.json`

**Interfaces:**
- `buildFields(schema) -> Field[]`
- `applyDefaults(schema, value) -> object`
- `validateValue(definition, value) -> string`
- Component expose: `validate() -> {ok, missing, errors}`

- [ ] **Step 1：写纯函数失败测试**

```javascript
// frontend/tests/unit/schemaForm.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import {
  applyDefaults,
  buildFields,
  validateValue,
} from '../../src/utils/schemaForm.js'

test('integer remains integer and keeps constraints', () => {
  const [field] = buildFields({
    type: 'object',
    properties: {
      count: { type: 'integer', minimum: 1, maximum: 5, default: 2 },
    },
  })
  assert.equal(field.kind, 'integer')
  assert.equal(field.minimum, 1)
  assert.equal(field.maximum, 5)
  assert.equal(field.default, 2)
  assert.match(validateValue(field.definition, 2.5), /整数/)
})

test('defaults initialize missing values without overwriting input', () => {
  const schema = {
    properties: {
      count: { type: 'integer', default: 2 },
      mode: { type: 'string', enum: ['a', 'b'], default: 'a' },
    },
  }
  assert.deepEqual(applyDefaults(schema, { count: 4 }), { count: 4, mode: 'a' })
})

test('validates string pattern and uri format', () => {
  assert.match(validateValue({ type: 'string', pattern: '^a+$' }, 'bbb'), /格式/)
  assert.match(validateValue({ type: 'string', format: 'uri' }, 'not url'), /URL/)
  assert.equal(validateValue({ type: 'string', format: 'uri' }, 'https://a.test'), '')
})

test('marks nested and combinator schemas for advanced JSON', () => {
  const fields = buildFields({
    properties: {
      nested: { type: 'object', properties: { x: { type: 'string' } } },
      choice: { oneOf: [{ type: 'string' }, { type: 'number' }] },
    },
  })
  assert.equal(fields[0].advanced, true)
  assert.equal(fields[1].advanced, true)
})
```

- [ ] **Step 2：加入单测脚本并确认失败**

`package.json`：

```json
"test:unit": "node --test tests/unit/*.test.mjs"
```

Run:

```powershell
cd E:\eval-platform\frontend
npm run test:unit
```

Expected: FAIL，`schemaForm.js` 不存在。

- [ ] **Step 3：实现 Schema 纯函数**

`buildFields` 每个 field 保留完整 `definition`，并输出：

```javascript
{
  key, label, description, required, kind,
  enum: definition.enum || [],
  default: definition.default,
  minimum, maximum, exclusiveMinimum, exclusiveMaximum,
  minLength, maxLength, pattern, format,
  advanced: Boolean(
    definition.$ref || definition.oneOf || definition.anyOf ||
    definition.allOf || (definition.type === 'object' && definition.properties)
  ),
}
```

`validateValue`：
- integer 用 `Number.isInteger`；
- number 用 `Number.isFinite`；
- 实现 minimum/maximum/exclusive 边界；
- string 实现长度、pattern、email、uri、date；
- array/object 检查真实类型；
- 空值的 required 检查仍由组件统一处理。

- [ ] **Step 4：组件保留复杂字段原文和错误**

组件新增：

```javascript
const drafts = reactive({})
const fieldErrors = reactive({})

function setComplex(field, text) {
  drafts[field.key] = text
  if (!text.trim()) {
    delete fieldErrors[field.key]
    set(field.key, undefined)
    return
  }
  try {
    const parsed = JSON.parse(text)
    const error = validateValue(field.definition, parsed)
    if (error) {
      fieldErrors[field.key] = error
      return
    }
    delete fieldErrors[field.key]
    set(field.key, parsed)
  } catch (error) {
    fieldErrors[field.key] = jsonErrorMessage(error, text)
  }
}
```

要求：
- 非法 JSON 不调用 `set()`，所以 modelValue 不会变成字符串；
- textarea 绑定 `drafts[field.key]`；
- schema 或 modelValue 变化时，只在没有未解决错误时同步 draft；
- `jsonErrorMessage` 至少返回 `JSON 无效: <message>`；若运行时错误含 position，则计算行号；
- 字段下用 `role="alert"` 显示错误。

- [ ] **Step 5：应用 defaults 与数字限制**

监听 schema，调用 `applyDefaults`，只有结果不同才 emit，避免循环。

integer：

```vue
<el-input-number
  v-else-if="field.kind === 'integer'"
  :model-value="modelValue[field.key]"
  :step="1"
  :precision="0"
  :min="field.minimum"
  :max="field.maximum"
  @update:model-value="set(field.key, $event)"
/>
```

number 不设置 precision；两者均显示边界说明。

- [ ] **Step 6：完善 validate()**

```javascript
validate() {
  const errors = { ...fieldErrors }
  const missing = []
  for (const field of fields.value) {
    const value = props.modelValue[field.key]
    if (field.required && (value === undefined || value === null || value === '')) {
      missing.push(field.key)
      errors[field.key] = '必填'
      continue
    }
    const message = validateValue(field.definition, value)
    if (message) errors[field.key] = message
  }
  Object.assign(fieldErrors, errors)
  return { ok: !missing.length && !Object.keys(errors).length, missing, errors }
}
```

- [ ] **Step 7：运行前端单测与构建**

Run:

```powershell
npm run test:unit
npm run build
```

Expected: 单测 PASS，Vite build 成功。

- [ ] **Step 8：记录文件清单**

记录 Task 10 全部文件。

## Task 11：试用台接入服务端调用历史

**Files:**
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/views/Resources.vue`
- Modify: `frontend/src/components/StatusBadge.vue`

**Interfaces:**
- `resourcesApi.calls(id, params)`

- [ ] **Step 1：增加 API 方法**

```javascript
calls: (id, params) =>
  request.get(`/resources/calls/${encodeURIComponent(id)}`, { params }),
```

注意：项目 axios 的 base URL 已含 `/api`，不重复添加。

- [ ] **Step 2：修正试用结果判定**

当前只识别 `failed/error/denied`，改为严格正向：

```javascript
const status = String(res.body?.status || '').toLowerCase()
const error = res.body?.error || null
const ok = status === 'success' && !error
trialResult.value = {
  ok,
  statusText: ok ? '执行成功' : `执行失败${error?.code ? ` (${error.code})` : ''}`,
  latency_ms: null,
  browser_latency_ms: Math.round(performance.now() - started),
  error_code: error?.code || '',
  summary: ok ? res.body?.result : error,
  raw: res,
}
```

产品文案分别写“服务端执行耗时”和“浏览器等待耗时”，未知不能显示 0。

- [ ] **Step 3：Schema 验证显示具体错误**

```javascript
const validation = schemaFormRef.value.validate()
if (!validation.ok) {
  const first = Object.entries(validation.errors)[0]
  ElMessage.error(first ? `${first[0]}：${first[1]}` : '请检查输入')
  return
}
```

- [ ] **Step 4：增加最近调用区**

状态：

```javascript
const callHistory = ref([])
const callHistoryTotal = ref(0)
const callHistoryLoading = ref(false)
const callHistoryError = ref('')
```

`openTrial` 和每次 `runTrial` 结束后调用：

```javascript
async function loadCallHistory() {
  if (!trialRow.value) return
  callHistoryLoading.value = true
  callHistoryError.value = ''
  try {
    const result = await resourcesApi.calls(trialRow.value.resource_id, {
      page: 1, page_size: 10,
    })
    callHistory.value = result.items || []
    callHistoryTotal.value = result.total || 0
  } catch (error) {
    callHistoryError.value = error?.response?.data?.message || error.message
  } finally {
    callHistoryLoading.value = false
  }
}
```

模板展示 status、server latency、version、trace、created_at，失败时展示脱敏 error；加载/空/失败分别有状态，不把失败伪装为空数组。

- [ ] **Step 5：增加 blocked 状态样式**

`StatusBadge.vue`：

```javascript
blocked: { label: '已阻断', tone: 'warning' },
```

调用状态 blocked/denied 映射为 blocked，不映射为 completed。

- [ ] **Step 6：响应式调整**

试用对话框：

```vue
<el-dialog width="min(900px, calc(100vw - 24px))">
```

为左右列增加断点：宽屏各 12，窄屏各 24；历史表放独立横向滚动容器，页面主区不横滚。

- [ ] **Step 7：静态验证**

Run:

```powershell
cd E:\eval-platform\frontend
npm run test:unit
npm run verify:ux-static
npm run build
```

Expected: PASS。

- [ ] **Step 8：记录文件清单**

记录 Task 11 全部文件。

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

## Task 14：全量回归与浏览器验收

**Files:**
- Create: `docs/superpowers/evidence/subproject-a.md`
- Modify only if verification exposes a regression in Tasks 1–13.

**Interfaces:**
- Evidence records: case id、commit/worktree state、environment、result、IDs、assertions、artifact refs、blocking reason。

- [ ] **Step 1：后端定向回归**

Run:

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_isolation_guard `
  tests.test_review_followup_a `
  tests.test_review_followup_d1 `
  tests.test_review_followup_d2 `
  tests.test_tool_gateway `
  tests.test_agent_runtime `
  tests.test_ops_governance -v
```

Expected: 全部 PASS。失败时先修复，再继续；不得把 fail 写成 pass。

- [ ] **Step 2：完整隔离后端回归**

Run:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Expected: 全部 PASS；输出无 `database is locked`。记录 test count 与耗时。

- [ ] **Step 3：前端验证**

Run:

```powershell
cd E:\eval-platform\frontend
npm run test:unit
npm run collect-permissions
npm run verify:ux-static
npm run build
```

Expected: 全部 PASS。检查权限收集 diff，仅允许已有 `resource:*`。

- [ ] **Step 4：启动隔离验收环境**

使用独立路径：

```powershell
$env:DATABASE_URL="sqlite+aiosqlite:///E:/eval-platform/backend/tests/_isolated/a_ui.db"
$env:UPLOAD_DIR="E:/eval-platform/backend/tests/_isolated/a_ui_uploads"
$env:LOG_DIR="E:/eval-platform/backend/tests/_isolated/a_ui_logs"
$env:BACKUP_DIR="E:/eval-platform/backend/tests/_isolated/a_ui_backups"
$env:MCP_STDIO_ALLOWLIST='{"stats-local":["E:\\eval-platform\\backend\\.venv\\Scripts\\python.exe","-m","tools.stats_service.stdio_server"]}'
```

分别启动：
- stats service：`tools\stats_service\run.ps1`
- backend：`.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- frontend：`npm run dev -- --host 127.0.0.1`

启动前检查端口；只结束本轮启动的进程。

- [ ] **Step 5：浏览器验收 HTTP 工具**

以管理员登录：
1. 资源 → 注册向导 → Tool；
2. endpoint 填 `http://127.0.0.1:8765/v1/parse`；
3. 输入 schema 含 `text` 必填；
4. 注册后试用 `{"text":"100 cm, 2 m"}`；
5. 断言执行成功，最近调用刷新后仍存在；
6. 输入缺失，断言业务失败不显示绿色。

保存 1440px 与 390px 截图。

- [ ] **Step 6：浏览器验收两步 Skill**

再注册 `/v1/stats` 工具；注册 Skill：
- s1 调 parse，input 绑定 `$input.text`；
- s2 调 stats，values 绑定 `s1.output.values`，target_unit 绑定 `$input.target_unit`。

试用：

```json
{"text":"100 cm, 2 m, 500 mm","target_unit":"m"}
```

断言 converted 为 `[1,2,0.5]`，mean 与 `3.5 / 3` 的误差小于 `1e-9`；两个工具历史都有 source `skill_step` 与同一父 correlation。

- [ ] **Step 7：浏览器验收 MCP**

Streamable HTTP：
1. 注册 endpoint `http://127.0.0.1:8765/mcp`；
2. 验证协商，断言协议版本/服务器名；
3. 获取目录，断言两个工具（证明分页聚合）；
4. 表单调用成功；
5. 空 values 调用，断言 `MCP_TOOL_ERROR` 且第五步为失败。

stdio：
1. 注册 command alias `stats-local`；
2. 获取目录并调用 parse；
3. 断言成功；
4. 确认 UI 没有任意 command 输入框。

保存关键步骤截图。

- [ ] **Step 8：证据文档**

创建 `docs/superpowers/evidence/subproject-a.md`，每个用例按以下格式填写真实值：

```markdown
## A-REV07a
- Result: pass | fail | blocked | not_run
- Environment: isolated a_ui.db
- Worktree: `git rev-parse HEAD` + `git status --short`
- Resource IDs:
- Correlation / trace IDs:
- Assertions:
- Screenshots:
- Blocking reason:
```

覆盖 A-REV07a/b、A-REV08、A-REV09、A-REV11、A-MCP、A-ISO、A-FULL、A-UI。`not_run`/`blocked` 必须写原因。

- [ ] **Step 9：最终检查**

Run:

```powershell
git status --short
git diff --check
```

Expected: `git diff --check` 无错误；不出现业务库、明文秘密、运行日志或新增 `__pycache__`。本任务不提交。
