<template>
  <div class="service-portal">
    <header class="portal-header">
      <div><span class="eyebrow">ENTERPRISE EVALUATION</span><h2>评测服务</h2><p>从模型接入到报告交付，为企业团队提供可追踪的评测服务。</p></div>
      <div class="header-actions">
        <el-select v-model="workspaceId" aria-label="企业工作空间" placeholder="选择工作空间" @change="switchWorkspace"><el-option v-for="w in workspaces" :key="w.id" :value="w.id" :label="w.name" /></el-select>
        <el-button v-if="userStore.hasPermission('service:create')" type="primary" :disabled="!workspaceId" @click="open('evaluation')">提交评测需求</el-button>
      </div>
    </header>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="load-error" />
    <section class="overview" aria-label="服务概览">
      <div><span>企业工作空间</span><strong>{{ workspaces.find(w => w.id === workspaceId)?.name || '待创建' }}</strong><small>企业成员共享服务与评测资产</small></div>
      <div><span>已注册模型服务</span><strong>{{ routes.length }}</strong><small>多版本并存 · 按比例灰度路由</small></div>
      <div><span>本月实际 Token</span><strong>{{ number(usage.tokens) }}</strong><small>在途任务预占单独计入额度</small></div>
      <div><span>本月计量金额</span><strong>¥ {{ (usage.amount / 100).toFixed(2) }}</strong><small>人民币 · 不代表已收款</small></div>
    </section>
    <el-tabs v-model="tab" class="portal-tabs">
      <el-tab-pane label="需求与交付" name="orders">
        <div class="section-heading"><div><h3>评测任务</h3><p>自动化模式直接入队；专家模式确认配置后执行。每 15 秒更新进度。</p></div><el-button :loading="loading" @click="loadWorkspace">刷新</el-button></div>
        <el-table v-loading="loading" :data="calls" stripe>
          <template #empty><el-empty description="暂无评测调用，准备好接入方和模型服务后即可提交需求。" /></template>
          <el-table-column prop="title" label="需求 / 调用" min-width="180" />
          <el-table-column label="配置模式" width="110"><template #default="{ row }">{{ row.mode === 'expert' ? '专家模式' : row.mode === 'auto' ? '自动化' : '—' }}</template></el-table-column>
          <el-table-column label="执行状态" width="130"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
          <el-table-column label="进度" width="140"><template #default="{ row }"><el-progress :percentage="row.progress || 0" /></template></el-table-column>
          <el-table-column label="实际 / 预占 Token" width="155"><template #default="{ row }">{{ number(row.tokens) }} / {{ number(row.reserved_tokens) }}</template></el-table-column>
          <el-table-column label="操作" min-width="180"><template #default="{ row }">
            <el-button v-if="userStore.hasPermission('service:run') && row.status === 'draft'" link type="primary" @click="act(() => api.start(row.id))">确认执行</el-button>
            <el-button v-if="userStore.hasPermission('service:run') && ['draft','queued','running','paused_budget'].includes(row.status)" link type="danger" @click="cancel(row)">取消</el-button>
            <el-button v-if="userStore.hasPermission('service:view') && row.report_ready" link type="primary" @click="download(row)">下载报告</el-button>
            <el-tooltip v-if="row.detail" :content="row.detail"><span class="muted">拒绝原因</span></el-tooltip>
          </template></el-table-column>
        </el-table>
        <div class="paging"><el-button :disabled="page === 1" @click="changePage(-1)">上一页</el-button><span>第 {{ page }} 页 · 每页最多 50 条</span><el-button :disabled="calls.length < 50" @click="changePage(1)">下一页</el-button></div>
      </el-tab-pane>
      <el-tab-pane label="模型服务与版本" name="models">
        <div class="section-heading"><div><h3>服务注册与发现</h3><p>将企业共享模型的冻结版本发布为可调用服务；API 网关统一鉴权、限流与版本路由。</p></div><el-button v-if="userStore.hasPermission('service:publish')" :disabled="!workspaceId" @click="open('route')">注册模型服务</el-button></div>
        <el-empty v-if="!routes.length" description="尚未注册模型服务" />
        <div class="route-grid"><el-card v-for="r in routes" :key="r.id" shadow="never" class="route-card">
          <template #header><div class="route-title"><strong>{{ r.name }}</strong><el-tag :type="r.stable_id ? 'success' : 'info'">{{ r.stable_id ? '可调用' : '待发布' }}</el-tag></div></template>
          <p class="mono">服务 ID {{ r.id }} · POST /api/service-gateway/v1/evaluations</p>
          <div class="version-flow"><div><small>稳定版本</small><strong>{{ versionLabel(r, r.stable_id) }}</strong></div><div><small>灰度版本 · {{ r.gray_percent }}%</small><strong>{{ versionLabel(r, r.candidate_id) }}</strong></div></div>
          <div class="version-tags"><el-tag v-for="v in r.versions" :key="v.id" type="info">{{ v.version }}</el-tag><span v-if="!r.versions.length" class="muted">添加版本后配置稳定路由</span></div>
          <div class="route-actions"><el-button v-if="userStore.hasPermission('service:publish')" @click="open('version', r)">关联已有版本</el-button><el-button v-if="userStore.hasPermission('service:publish')" @click="open('endpoint', r)">注册模型接口</el-button><el-button v-if="userStore.hasPermission('service:publish')" :disabled="!r.versions.length" @click="open('traffic', r)">配置路由</el-button><el-button v-if="userStore.hasPermission('service:publish') && r.previous_id" link @click="rollback(r)">回滚</el-button></div>
        </el-card></div>
      </el-tab-pane>
      <el-tab-pane label="接入方与用量账单" name="usage">
        <div class="section-heading"><div><h3>接入方配额</h3><p>每日 / 每月按北京时间重置。费用按调用时单价与实际 Token 计量，密钥仅在创建时显示。</p></div><el-button v-if="userStore.hasPermission('service:credential')" :disabled="!workspaceId" @click="open('client')">创建接入方</el-button></div>
        <el-table :data="clients">
          <template #empty><el-empty description="创建接入方后，由服务运营分配额度与单价。" /></template>
          <el-table-column prop="name" label="接入方" min-width="140" />
          <el-table-column label="密钥" width="160"><template #default="{ row }"><code>{{ row.key_prefix }}…</code><div class="muted">{{ row.active ? '有效' : '已撤销' }}</div></template></el-table-column>
          <el-table-column label="每日使用 / 额度" min-width="165"><template #default="{ row }">{{ number(row.usage.daily_used) }} / {{ number(row.daily_tokens) }}<el-progress :percentage="percent(row.usage.daily_used, row.daily_tokens)" :show-text="false" /></template></el-table-column>
          <el-table-column label="每月使用 / 额度" min-width="165"><template #default="{ row }">{{ number(row.usage.monthly_used) }} / {{ number(row.monthly_tokens) }}<el-progress :percentage="percent(row.usage.monthly_used, row.monthly_tokens)" :show-text="false" /></template></el-table-column>
          <el-table-column label="限流 / 单价" width="150"><template #default="{ row }">{{ row.requests_per_minute }} 次/分钟<div class="muted">¥{{ (row.price_fen_per_1k / 100).toFixed(2) }} / 千 Token</div></template></el-table-column>
          <el-table-column label="计量金额" width="100"><template #default="{ row }">¥{{ (row.usage.amount_fen / 100).toFixed(2) }}</template></el-table-column>
          <el-table-column label="操作" width="130"><template #default="{ row }"><el-button v-if="userStore.hasPermission('service:credential') && row.active" link type="danger" @click="revoke(row)">撤销</el-button><el-button v-if="userStore.hasPermission('service:admit')" link @click="open('quota', row)">额度</el-button></template></el-table-column>
        </el-table>
        <div class="api-guide"><h3>API 接入</h3><p>请求头携带 X-API-Key 与唯一的 Idempotency-Key。重复提交相同幂等键返回同一评测调用，不重复预占额度。</p><pre>{{ apiExample }}</pre><p>使用返回的调用 ID 查询 GET /api/service-gateway/v1/evaluations/{id}，完成后从 /{id}/report 下载正式报告。</p></div>
        <h3>网关访问审计</h3><p>记录每次 API 请求，包括幂等重试、参数错误和已知密钥的鉴权失败。</p><el-table :data="gatewayAudit"><el-table-column prop="created_at" label="时间（UTC）" min-width="180" /><el-table-column prop="client_id" label="接入方" width="90" /><el-table-column prop="method" label="方法" width="80" /><el-table-column prop="path" label="请求路径" min-width="220" /><el-table-column prop="status_code" label="HTTP 状态" width="100" /></el-table><div class="paging"><el-button :disabled="page === 1" @click="changePage(-1)">上一页</el-button><span>第 {{ page }} 页</span><el-button :disabled="calls.length < 50 && gatewayAudit.length < 50" @click="changePage(1)">下一页</el-button></div>
        <h3>调用审计与计量明细</h3><el-table :data="calls"><el-table-column prop="id" label="调用 ID" width="90" /><el-table-column prop="client_id" label="接入方 ID" width="100" /><el-table-column prop="created_at" label="时间（UTC）" min-width="180" /><el-table-column label="状态"><template #default="{ row }">{{ statusLabel(row.status) }}</template></el-table-column><el-table-column prop="tokens" label="实际 Token" /><el-table-column label="金额 / 计量"><template #default="{ row }">¥{{ (row.amount_fen / 100).toFixed(2) }} · {{ row.billing_status === 'settled' ? '已计量' : row.billing_status === 'pending' ? '执行中' : row.billing_status === 'unmeasured' ? '待核量' : '未计费' }}</template></el-table-column></el-table>
      </el-tab-pane>
      <el-tab-pane label="企业空间与资产" name="team">
        <div class="section-heading"><div><h3>团队协作</h3><p>同一企业成员共享工作空间、服务任务和已发布资产，跨企业数据隔离。</p></div><div><el-button v-if="userStore.hasPermission('service:workspace')" @click="open('workspace')">新建空间</el-button><el-button v-if="userStore.hasPermission('service:workspace')" @click="open('member')">添加成员</el-button><el-button v-if="userStore.hasPermission('service:admit')" @click="open('customer')">开通企业客户</el-button><el-button v-if="userStore.hasPermission('service:admit')" @click="open('grant')">交付评测数据集</el-button><el-button v-if="userStore.hasPermission('service:admit')" @click="open('quota')">按接入方 ID 分配额度</el-button></div></div>
        <el-table :data="members"><el-table-column prop="username" label="企业成员" /><el-table-column label="账号状态"><template #default="{ row }">{{ row.status === 'active' ? '正常' : '已停用' }}</template></el-table-column></el-table>
        <div class="asset-grid"><el-card shadow="never"><template #header>共享数据集 · {{ assets.datasets.length }}</template><p class="muted">服务运营发布并授权给本企业的评测数据集。</p><p v-for="d in assets.datasets" :key="d.id">{{ d.name }} <small>#{{ d.id }}</small></p><el-empty v-if="!assets.datasets.length" description="暂无可用数据集，请联系服务运营导入并发布企业评测资产。" :image-size="60" /></el-card><el-card shadow="never"><template #header>授权模型 · {{ assets.models.length }}</template><p class="muted">注册服务时选择已冻结的模型访问配置。</p><p v-for="m in assets.models" :key="m.id">{{ m.name }} <small>#{{ m.id }}</small></p><el-empty v-if="!assets.models.length" description="暂无可用模型，可在模型服务页注册服务与接口版本。" :image-size="60" /></el-card></div>
      </el-tab-pane>
    </el-tabs>
    <el-dialog v-model="dialog" :title="dialogTitle" width="min(600px, 94vw)" :close-on-click-modal="false">
      <el-form label-position="top" @submit.prevent="save">
        <template v-if="kind === 'evaluation'">
          <el-form-item label="评测标题"><el-input v-model="form.title" maxlength="200" /></el-form-item>
          <el-form-item label="配置方式"><el-radio-group v-model="form.mode"><el-radio-button value="auto">自动化模式</el-radio-button><el-radio-button value="expert">专家模式</el-radio-button></el-radio-group><p class="muted">{{ form.mode === 'auto' ? '使用标准精确匹配评测，提交后自动入队。' : '自定义场景和裁判工具，生成配置后确认执行。' }}</p></el-form-item>
          <el-form-item label="接入方"><el-select v-model="form.client_id"><el-option v-for="c in clients.filter(c => c.active)" :key="c.id" :value="c.id" :label="c.name" /></el-select></el-form-item>
          <el-form-item label="模型服务"><el-select v-model="form.route_id"><el-option v-for="r in routes.filter(r => r.stable_id)" :key="r.id" :value="r.id" :label="r.name" /></el-select></el-form-item>
          <el-form-item label="共享数据集"><el-select v-model="form.dataset_id"><el-option v-for="d in assets.datasets" :key="d.id" :value="d.id" :label="d.name" /></el-select></el-form-item>
          <el-form-item label="Token 预算"><el-input-number v-model="form.token_budget" :min="1" :max="100000000" /><small class="muted">提交时预占，结束后按实际用量计量。</small></el-form-item>
          <template v-if="form.mode === 'expert'"><el-form-item label="场景"><el-input v-model="form.scene" /></el-form-item><el-form-item label="裁判工具"><el-select v-model="form.judge_resource_id"><el-option label="精确匹配" value="builtin/exact_match" /><el-option label="包含匹配" value="builtin/contains" /></el-select></el-form-item></template>
          <el-form-item label="定制化需求"><el-input v-model="form.requirement" type="textarea" :rows="3" maxlength="10000" /></el-form-item>
        </template>
        <template v-else-if="kind === 'endpoint'"><el-form-item label="服务版本名"><el-input v-model="form.version" /></el-form-item><el-form-item label="OpenAI 兼容接口地址"><el-input v-model="form.api_url" placeholder="https://允许的域名/v1" /></el-form-item><el-form-item label="上游模型标识"><el-input v-model="form.served_model_name" /></el-form-item><el-form-item label="上游 API Key"><el-input v-model="form.api_key" type="password" show-password autocomplete="new-password" /></el-form-item><p class="muted">仅接入运营允许的 HTTPS 域名。注册后冻结访问配置，凭据不对团队成员展示。</p></template>
        <template v-else-if="kind === 'version'"><el-form-item label="服务版本名"><el-input v-model="form.version" placeholder="例如 v1.0" /></el-form-item><el-form-item label="授权模型"><el-select v-model="form.model_id" @change="form.model_version_id = null"><el-option v-for="m in assets.models" :key="m.id" :value="m.id" :label="m.name" /></el-select></el-form-item><el-form-item label="冻结模型版本"><el-select v-model="form.model_version_id"><el-option v-for="v in assets.versions.filter(v => v.model_id === form.model_id)" :key="v.id" :value="v.id" :label="v.version" /></el-select></el-form-item></template>
        <template v-else-if="kind === 'traffic'"><el-form-item label="稳定版本"><el-select v-model="form.stable_id"><el-option v-for="v in selected.versions" :key="v.id" :value="v.id" :label="v.version" /></el-select></el-form-item><el-form-item label="灰度版本"><el-select v-model="form.candidate_id" clearable><el-option v-for="v in selected.versions.filter(v => v.id !== form.stable_id)" :key="v.id" :value="v.id" :label="v.version" /></el-select></el-form-item><el-form-item label="灰度流量比例"><el-slider v-model="form.gray_percent" :max="100" show-input /></el-form-item><p class="muted">影响此后提交的任务；已创建任务保持原版本。此操作不代表质量门禁已通过。</p></template>
        <template v-else-if="kind === 'grant'"><el-form-item label="目标客户企业 ID"><el-input-number v-model="form.tenant_id" :min="1" /></el-form-item><el-form-item label="已发布且质检通过的数据集 ID"><el-input-number v-model="form.dataset_id" :min="1" /></el-form-item><p class="muted">复制已发布版本及其评测样本到客户企业，保留来源审计与原始质检信息。</p></template><template v-else-if="kind === 'quota'"><el-form-item label="接入方 ID"><el-input-number v-model="form.id" :min="1" /></el-form-item><el-form-item label="每日 Token 额度"><el-input-number v-model="form.daily_tokens" :min="0" :max="2000000000" /></el-form-item><el-form-item label="每月 Token 额度"><el-input-number v-model="form.monthly_tokens" :min="0" :max="2000000000" /></el-form-item><el-form-item label="每分钟请求数"><el-input-number v-model="form.requests_per_minute" :min="1" :max="1000" /></el-form-item><el-form-item label="单价（分 / 千 Token）"><el-input-number v-model="form.price_fen_per_1k" :min="0" :max="1000000" /></el-form-item></template>
        <template v-else-if="['member','customer'].includes(kind)"><el-form-item v-if="kind === 'customer'" label="企业名称"><el-input v-model="form.company" /></el-form-item><el-form-item label="登录账号"><el-input v-model="form.username" autocomplete="off" /></el-form-item><el-form-item label="初始密码（至少 12 字符）"><el-input v-model="form.password" type="password" show-password autocomplete="new-password" /></el-form-item></template>
        <el-form-item v-else label="名称"><el-input v-model="form.name" maxlength="120" /></el-form-item>
        <el-alert v-if="formError" :title="formError" type="error" :closable="false" />
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button v-if="userStore.hasPermission(dialogPermission)" type="primary" :loading="saving" @click="save">{{ kind === 'evaluation' ? '提交需求' : '保存' }}</el-button></template>
    </el-dialog>
    <el-dialog v-model="showKey" title="请保存接入密钥" width="min(560px, 94vw)" @closed="createdKey = ''"><el-alert title="密钥仅展示一次，关闭后无法恢复。新接入方额度为 0，请联系服务运营分配。" type="warning" :closable="false" /><pre class="secret">{{ createdKey }}</pre></el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { servicePortalApi as api } from '@/api'
import { useUserStore } from '@/stores/user'
const userStore = useUserStore()
const workspaces = ref([]), workspaceId = ref(null), clients = ref([]), routes = ref([]), calls = ref([]), members = ref([]), gatewayAudit = ref([])
const assets = ref({ datasets: [], models: [], versions: [] })
const tab = ref('orders'), page = ref(1), loading = ref(false), error = ref(''), dialog = ref(false), kind = ref(''), form = ref({}), selected = ref(null), saving = ref(false), formError = ref('')
const showKey = ref(false), createdKey = ref('')
let timer, requestKey = '', generation = 0, disposed = false
const titles = { evaluation: '提交评测需求', route: '注册模型服务', client: '创建接入方', workspace: '新建企业空间', member: '添加企业成员', customer: '开通外部企业客户', version: '添加服务版本', traffic: '版本与灰度路由', quota: '配额与计费设置', endpoint: '注册模型接口版本', grant: '向客户企业交付数据集' }
const permissionMap = { evaluation: 'service:create', route: 'service:publish', version: 'service:publish', traffic: 'service:publish', client: 'service:credential', workspace: 'service:workspace', member: 'service:workspace', customer: 'service:admit', quota: 'service:admit', endpoint: 'service:publish', grant: 'service:admit' }
const dialogTitle = computed(() => titles[kind.value])
const dialogPermission = computed(() => permissionMap[kind.value])
const usage = computed(() => clients.value.reduce((a, c) => ({ tokens: a.tokens + c.usage.measured_tokens, amount: a.amount + c.usage.amount_fen }), { tokens: 0, amount: 0 }))
const number = n => Number(n || 0).toLocaleString('zh-CN')
const percent = (used, total) => total ? Math.min(100, Math.round(used / total * 100)) : 0
const versionLabel = (route, id) => route.versions.find(v => v.id === id)?.version || '未配置'
const statusLabel = s => ({ draft: '待确认配置', queued: '排队中', running: '评测中', success: '已完成', partial_failed: '部分失败', failed: '失败', cancelled: '已取消', paused_budget: '预算已用尽', rejected: '调用被拒绝' }[s] || s)
const statusType = s => s === 'success' ? 'success' : ['failed','rejected'].includes(s) ? 'danger' : ['running','paused_budget'].includes(s) ? 'warning' : 'info'
const message = e => { const d = e?.response?.data; return typeof d?.detail === 'string' ? d.detail : d?.message || e?.message || '操作失败，请重试' }
const apiExample = computed(() => JSON.stringify({ client_id: clients.value[0]?.id || '<接入方 ID>', route_id: routes.value[0]?.id || '<服务 ID>', title: '模型能力评测', mode: 'auto', dataset_id: assets.value.datasets[0]?.id || '<数据集 ID>', token_budget: 10000 }, null, 2))
async function loadWorkspace() {
  if (!workspaceId.value) return
  const run = ++generation, id = workspaceId.value
  loading.value = true
  try {
    const [c, r, e, audit] = await Promise.all([api.clients(id), api.routes(id), api.evaluations(id, page.value), userStore.hasPermission('service:view') ? api.gatewayAudit(id, page.value) : Promise.resolve({ items: [] })])
    if (run !== generation) return
    clients.value = c.items; routes.value = r.items; calls.value = e.items; gatewayAudit.value = audit.items; error.value = ''
  } catch (e) { if (run === generation) error.value = message(e) }
  finally { if (run === generation) loading.value = false }
}
async function load() {
  try {
    const [w, a, m] = await Promise.all([api.workspaces(), api.assets(), api.members()])
    workspaces.value = w.items; assets.value = a; members.value = m.items
    if (!workspaceId.value) workspaceId.value = w.items[0]?.id || null
    await loadWorkspace()
  } catch (e) { error.value = message(e) }
}
function switchWorkspace() { page.value = 1; clients.value = []; routes.value = []; calls.value = []; loadWorkspace() }
function changePage(delta) { page.value += delta; loadWorkspace() }
function open(type, row = null) {
  kind.value = type; selected.value = row; formError.value = ''; requestKey = crypto.randomUUID()
  form.value = type === 'evaluation' ? { title: '', requirement: '', mode: 'auto', client_id: clients.value.find(c => c.active)?.id, route_id: routes.value.find(r => r.stable_id)?.id, dataset_id: assets.value.datasets[0]?.id, token_budget: 10000, scene: 'qa', judge_resource_id: 'builtin/exact_match' }
    : type === 'traffic' ? { stable_id: row.stable_id, candidate_id: row.candidate_id, gray_percent: row.gray_percent }
    : type === 'quota' ? { id: row?.id, daily_tokens: row?.daily_tokens || 0, monthly_tokens: row?.monthly_tokens || 0, requests_per_minute: row?.requests_per_minute || 30, price_fen_per_1k: row?.price_fen_per_1k || 0 } : {}
  dialog.value = true
}
async function save() {
  if (saving.value) return
  saving.value = true; formError.value = ''
  try {
    const data = { ...form.value }, ws = { ...data, workspace_id: workspaceId.value }
    if (kind.value === 'evaluation') { if (!data.title?.trim() || !data.client_id || !data.route_id || !data.dataset_id) throw new Error('请填写标题并选择接入方、模型服务与共享数据集'); await api.evaluate(data, requestKey) }
    else if (kind.value === 'route') await api.register(ws)
    else if (kind.value === 'client') { const result = await api.createClient(ws); createdKey.value = result.api_key; showKey.value = true }
    else if (kind.value === 'workspace') { const w = await api.createWorkspace(data); workspaceId.value = w.id }
    else if (kind.value === 'grant') await api.grant(data)
    else if (kind.value === 'member') await api.createMember(data)
    else if (kind.value === 'customer') { const r = await api.onboard(data); ElMessage.success(`企业已开通，企业 ID：${r.tenant_id}，工作空间 ID：${r.workspace_id}`) }
    else if (kind.value === 'endpoint') await api.endpoint(selected.value.id, data)
    else if (kind.value === 'version') await api.version(selected.value.id, data)
    else if (kind.value === 'traffic') await api.traffic(selected.value.id, { ...data, candidate_id: data.candidate_id || null })
    else if (kind.value === 'quota') await api.quota(data.id, data)
    dialog.value = false; form.value = {}; ElMessage.success('已保存'); await load()
  } catch (e) { formError.value = message(e) } finally { saving.value = false }
}
async function act(fn) { try { await fn(); await loadWorkspace() } catch (e) { ElMessage.error(message(e)) } }
async function confirmAction(text, fn) { try { await ElMessageBox.confirm(text, '确认操作', { type: 'warning' }); await act(fn) } catch (_) { /* User cancelled. */ } }
const revoke = row => confirmAction(`撤销 ${row.name} 的密钥后，新请求将被拒绝。`, () => api.revoke(row.id))
const rollback = row => confirmAction(`将 ${row.name} 切回上一稳定版本并关闭灰度流量。`, () => api.rollback(row.id))
const cancel = row => confirmAction('取消此评测任务？已发生的实际用量仍会计量。', () => api.cancel(row.id))
async function download(row) { try { const blob = await api.report(row.id); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `evaluation-${row.id}.json`; a.click(); URL.revokeObjectURL(url) } catch (e) { ElMessage.error(message(e)) } }
onMounted(async () => { await load(); if (disposed) return; timer = setInterval(() => { if (!dialog.value && !loading.value && !document.hidden) loadWorkspace() }, 15000) })
onUnmounted(() => { disposed = true; clearInterval(timer); generation++ })
</script>

<style scoped>
.service-portal { --portal-accent: #147d75; }
.portal-header { display: flex; justify-content: space-between; align-items: center; gap: 24px; margin-bottom: 28px; }
.eyebrow { color: var(--portal-accent); font-size: 11px; letter-spacing: .16em; font-weight: 700; }
h2 { font-size: 28px; margin: 8px 0; letter-spacing: -.04em; } h3 { font-size: 16px; margin: 0 0 8px; }
p { line-height: 1.7; color: var(--text-secondary); font-size: 13px; margin: 6px 0; }
.header-actions { display: flex; gap: 12px; } .header-actions .el-select { width: 190px; }
.overview { display: grid; grid-template-columns: 1.3fr 1fr 1fr 1fr; border: 1px solid var(--el-border-color-light); border-top: 3px solid var(--portal-accent); background: var(--el-bg-color); margin-bottom: 28px; }
.overview > div { padding: 22px; border-right: 1px solid var(--el-border-color-light); min-width: 0; }.overview > div:last-child { border: 0; }
.overview span, .overview small { display: block; color: var(--text-secondary); font-size: 12px; }.overview strong { display: block; font-size: 25px; font-weight: 600; margin: 10px 0; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.overview > div:first-child strong { font-size: 20px; }
.portal-tabs { background: var(--el-bg-color); padding: 8px 22px 24px; border: 1px solid var(--el-border-color-light); }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 18px 0 22px; }.section-heading p { max-width: 720px; }
.route-grid, .asset-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }.asset-grid { margin-top: 24px; }
.route-title { display: flex; align-items: center; justify-content: space-between; }.mono { font-family: Consolas, monospace; font-size: 11px; overflow-wrap: anywhere; }
.version-flow { display: grid; grid-template-columns: 1fr 1fr; border-left: 3px solid var(--portal-accent); background: var(--el-fill-color-light); margin: 18px 0; padding: 14px; }.version-flow small, .version-flow strong { display: block; }.version-flow small { color: var(--text-secondary); margin-bottom: 8px; }
.version-tags { display: flex; gap: 8px; flex-wrap: wrap; min-height: 25px; }.route-actions { margin-top: 22px; display: flex; gap: 8px; flex-wrap: wrap; }.route-actions .el-button { margin-left: 0; }
.muted { color: var(--text-secondary); font-size: 12px; }.paging { display: flex; justify-content: flex-end; gap: 15px; align-items: center; margin-top: 20px; font-size: 12px; }.api-guide { background: var(--el-fill-color-light); margin: 28px 0; padding: 20px; border-left: 3px solid var(--portal-accent); }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; line-height: 1.65; }.secret { padding: 18px; background: var(--el-fill-color-light); user-select: all; }.load-error { margin-bottom: 18px; }.el-form .el-select { width: 100%; }.el-form small { margin-left: 10px; }
@media (max-width: 1000px) { .portal-header, .section-heading { align-items: flex-start; flex-direction: column; }.overview { grid-template-columns: repeat(2, 1fr); }.route-grid, .asset-grid { grid-template-columns: 1fr; } }
@media (max-width: 600px) { .header-actions { flex-direction: column; width: 100%; }.header-actions .el-select { width: 100%; }.overview { grid-template-columns: 1fr; }.overview > div { border-right: 0; border-bottom: 1px solid var(--el-border-color-light); }.portal-tabs { padding: 8px; } }
</style>
