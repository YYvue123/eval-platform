# Task 11：试用台接入服务端调用历史

Work from E:\eval-platform. Do not git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>". Do not implement Task 12 wizard or Task 13 MCP workbench beyond what this task needs.

Backend already has GET /api/resources/calls/{rid:path} (resource:view). SchemaForm.validate() now returns {ok, missing, errors} and rebuilds errors each call — show first errors entry, not only missing.

If StatusBadge already has extra phases from earlier D1 work, keep them and add blocked if missing.

Unknown server latency must not display as 0; use history item latency_ms when present, otherwise an em dash.

## Global constraints

- 产品页面文案不写「禁止 Mock 假成功」等研发口号
- 请求失败不能 catch 后伪装 items=[]
- 不创建 commit

## Plan text

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

