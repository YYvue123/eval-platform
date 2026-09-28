<template>
  <div class="resources-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">工具中心</h2>
        <p class="page-desc">发现、注册、试用工具 / Skill / MCP；真实调用，无 Mock 假成功。</p>
      </div>
      <div class="header-actions">
        <el-button v-if="userStore.hasPermission('resource:invoke')" @click="showBatch = true">冻结批次</el-button>
        <el-button v-if="userStore.hasPermission('resource:invoke')" @click="openMcpWorkbench()">MCP 连接</el-button>
        <el-button v-if="userStore.hasPermission('resource:create')" type="primary" @click="openWizard()">添加资源</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-tabs v-model="tab" @tab-change="onTabChange">
        <el-tab-pane label="全部" name="all" />
        <el-tab-pane label="工具" name="tool" />
        <el-tab-pane label="Skills" name="skill" />
        <el-tab-pane label="MCP 连接" name="mcp" />
      </el-tabs>

      <div class="toolbar">
        <el-input v-model="search" clearable placeholder="按名称或 resource_id 搜索" style="width: 260px" @keyup.enter="reloadFirst" />
        <el-select v-model="statusFilter" clearable placeholder="状态" style="width: 140px" @change="reloadFirst">
          <el-option label="online" value="online" />
          <el-option label="offline" value="offline" />
          <el-option label="pending" value="pending" />
        </el-select>
        <el-button @click="reloadFirst">搜索</el-button>
        <span class="hint">共 {{ total }} 条</span>
      </div>

      <el-table v-loading="loading" :data="items" stripe @row-click="openDetail">
        <el-table-column prop="name" label="名称" min-width="160">
          <template #default="{ row }">
            <div class="name-cell">
              <strong>{{ row.name }}</strong>
              <el-tag v-if="row.builtin" size="small" type="info">内置只读</el-tag>
            </div>
            <div class="sub">{{ row.description || row.resource_id }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="resource_type" label="类型" width="100" />
        <el-table-column label="来源" width="90">
          <template #default="{ row }">{{ row.builtin ? '平台' : '租户' }}</template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="90" />
        <el-table-column prop="health_status" label="健康" width="100">
          <template #default="{ row }">
            <StatusBadge :phase="healthPhase(row.health_status)" :text="row.health_status || 'unknown'" />
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="['tool','skill','mcp'].includes(row.resource_type) && userStore.hasPermission('resource:invoke')"
              link
              type="primary"
              size="small"
              @click.stop="openTrial(row)"
            >试用</el-button>
            <el-button
              v-if="row.resource_type === 'mcp' && userStore.hasPermission('resource:invoke')"
              link
              type="primary"
              size="small"
              @click.stop="openMcpWorkbench(row)"
            >连接</el-button>
            <el-button v-if="userStore.hasPermission('resource:view')" link size="small" @click.stop="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          layout="total, sizes, prev, pager, next"
          :total="total"
          :page-sizes="[20, 50, 100]"
          @current-change="loadData"
          @size-change="reloadFirst"
        />
      </div>
    </el-card>

    <!-- 详情抽屉 -->
    <el-drawer v-model="showDetail" :title="detail?.name || '资源详情'" size="480px">
      <template v-if="detail">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="resource_id">{{ detail.resource_id }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ detail.resource_type }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ detail.version }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ detail.status }} / {{ detail.health_status }}</el-descriptions-item>
          <el-descriptions-item label="内置">{{ detail.builtin ? '是（只读）' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="说明">{{ detail.description || '—' }}</el-descriptions-item>
        </el-descriptions>
        <p class="hint">调用次数 {{ detail.call_count ?? '—' }}（若无真实来源不展示成功率）</p>
        <el-collapse>
          <el-collapse-item title="输入 Schema" name="in">
            <pre class="payload">{{ pretty(inputSchema(detail)) }}</pre>
          </el-collapse-item>
          <el-collapse-item title="Manifest（已脱敏）" name="mf">
            <pre class="payload">{{ pretty(detail.manifest) }}</pre>
          </el-collapse-item>
        </el-collapse>
        <div class="drawer-actions">
          <el-button v-if="userStore.hasPermission('resource:invoke')" type="primary" @click="openTrial(detail)">试用</el-button>
          <el-button v-if="userStore.hasPermission('resource:view')" @click="runHealth(detail)">健康检查</el-button>
        </div>
        <el-alert
          v-if="!versionsSupported"
          type="info"
          :closable="false"
          title="版本列表 / 调用记录 API 未完整开放，详情不展示静态假数据"
          style="margin-top: 12px"
        />
      </template>
    </el-drawer>

    <!-- 试用台 -->
    <el-dialog v-model="showTrial" :title="`试用 · ${trialRow?.name || ''}`" width="900px" destroy-on-close @closed="onTrialClosed">
      <el-row :gutter="16">
        <el-col :span="12">
          <div class="panel-title">参数</div>
          <el-radio-group v-model="trialMode" size="small" style="margin-bottom: 8px">
            <el-radio-button value="form">Schema 表单</el-radio-button>
            <el-radio-button value="json">高级 JSON</el-radio-button>
          </el-radio-group>
          <SchemaForm v-show="trialMode === 'form'" ref="schemaFormRef" v-model="trialBody" :schema="trialSchema" />
          <el-input
            v-show="trialMode === 'json'"
            v-model="trialJsonText"
            type="textarea"
            :rows="14"
            @change="syncJsonToBody"
          />
          <el-alert
            v-if="sideEffectHint"
            type="warning"
            :closable="false"
            :title="sideEffectHint"
            style="margin-top: 8px"
          />
        </el-col>
        <el-col :span="12">
          <div class="panel-title">结果</div>
          <div v-if="!trialResult" class="hint">尚未调用</div>
          <template v-else>
            <StatusBadge :phase="trialResult.ok ? 'completed' : 'failed'" :text="trialResult.statusText" />
            <p class="hint">耗时 {{ trialResult.latency_ms ?? '—' }} ms · {{ trialResult.error_code || '' }}</p>
            <pre class="payload">{{ pretty(trialResult.summary) }}</pre>
            <el-collapse>
              <el-collapse-item title="原始响应（脱敏视图）" name="raw">
                <pre class="payload">{{ pretty(trialResult.raw) }}</pre>
              </el-collapse-item>
            </el-collapse>
            <el-button size="small" @click="copyTrial">复制 JSON</el-button>
          </template>
        </el-col>
      </el-row>
      <template #footer>
        <el-button @click="showTrial = false">关闭</el-button>
        <el-button type="primary" :loading="trialLoading" @click="runTrial">实际调用</el-button>
      </template>
    </el-dialog>

    <!-- 注册向导 -->
    <el-dialog v-model="showWizard" title="添加资源" width="760px" destroy-on-close @closed="resetWizard">
      <el-steps :active="wizardStep" finish-status="success" align-center style="margin-bottom: 16px">
        <el-step title="类型" />
        <el-step title="基本信息" />
        <el-step title="参数 / 连接" />
        <el-step title="校验" />
        <el-step title="确认" />
      </el-steps>

      <div v-if="wizardStep === 0">
        <el-radio-group v-model="wizard.kind">
          <el-radio value="tool">工具 Tool — 同步裁判/HTTP 工具</el-radio>
          <el-radio value="skill">Skill — 仅支持已实现的 workflow 类型</el-radio>
          <el-radio value="mcp">MCP — HTTP JSON-RPC（stdio 未支持）</el-radio>
        </el-radio-group>
        <el-alert type="info" :closable="false" style="margin-top: 12px" :title="kindIntro" />
      </div>

      <el-form v-else-if="wizardStep === 1" label-width="110px">
        <el-form-item label="命名空间" required>
          <el-input v-model="wizard.ns" placeholder="如 demo" />
        </el-form-item>
        <el-form-item label="标识" required>
          <el-input v-model="wizard.slug" placeholder="如 my_tool" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="wizard.name" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="wizard.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="版本">
          <el-input v-model="wizard.version" />
        </el-form-item>
        <el-form-item label="调用方式">
          <el-select v-model="wizard.call_mode" style="width: 200px">
            <el-option label="sync" value="sync" />
            <el-option label="async（未完整验收）" value="async" disabled />
          </el-select>
        </el-form-item>
      </el-form>

      <div v-else-if="wizardStep === 2">
        <template v-if="wizard.kind === 'mcp'">
          <el-form label-width="120px">
            <el-form-item label="Endpoint" required>
              <el-input v-model="wizard.endpoint" placeholder="https://..." />
            </el-form-item>
            <el-form-item label="Token">
              <el-input v-model="wizard.token" type="password" show-password placeholder="仅本次提交，不写入 localStorage" />
            </el-form-item>
            <el-form-item label="Egress 白名单">
              <el-input v-model="wizard.allowlist" placeholder="host1,host2" />
            </el-form-item>
          </el-form>
        </template>
        <template v-else>
          <p class="hint">配置输入 Schema（常见字段）；可切换高级 JSON，切换不丢字段。</p>
          <el-radio-group v-model="wizard.paramMode" size="small" style="margin-bottom: 8px">
            <el-radio-button value="form">字段编辑</el-radio-button>
            <el-radio-button value="json">高级 JSON Schema</el-radio-button>
          </el-radio-group>
          <div v-if="wizard.paramMode === 'form'">
            <div v-for="(f, idx) in wizard.fields" :key="idx" class="field-row">
              <el-input v-model="f.key" placeholder="字段名" style="width: 120px" />
              <el-select v-model="f.type" style="width: 110px">
                <el-option label="string" value="string" />
                <el-option label="number" value="number" />
                <el-option label="boolean" value="boolean" />
              </el-select>
              <el-checkbox v-model="f.required">必填</el-checkbox>
              <el-button link type="danger" @click="wizard.fields.splice(idx, 1)">删</el-button>
            </div>
            <el-button size="small" @click="wizard.fields.push({ key: '', type: 'string', required: false })">加字段</el-button>
          </div>
          <el-input v-else v-model="wizard.schemaJson" type="textarea" :rows="10" @blur="pullSchemaFromJson" />
        </template>
        <el-divider>专业入口</el-divider>
        <el-input v-model="wizard.rawManifest" type="textarea" :rows="6" placeholder="可选：粘贴完整 Manifest JSON，将覆盖向导字段" />
      </div>

      <div v-else-if="wizardStep === 3">
        <el-space direction="vertical" fill style="width: 100%">
          <el-tag :type="checks.schema ? 'success' : 'info'">结构合法：{{ checks.schema ? '通过' : '未测' }}</el-tag>
          <el-tag :type="checks.connect === true ? 'success' : checks.connect === false ? 'danger' : 'info'">
            连接探测：{{ checks.connect === true ? '成功' : checks.connect === false ? '失败' : '未执行' }}
          </el-tag>
          <el-tag type="info">实际调用：未执行（注册后在试用台验证）</el-tag>
        </el-space>
        <el-button style="margin-top: 12px" :loading="checking" @click="runWizardChecks">运行已实现检查</el-button>
        <pre v-if="checkLog" class="payload">{{ checkLog }}</pre>
      </div>

      <div v-else>
        <pre class="payload">{{ pretty(buildManifest()) }}</pre>
        <p class="hint">凭证仅在本次请求提交；列表/详情返回脱敏状态，不回显原文 token。</p>
      </div>

      <template #footer>
        <el-button @click="showWizard = false">取消</el-button>
        <el-button v-if="wizardStep > 0" @click="wizardStep -= 1">上一步</el-button>
        <el-button v-if="wizardStep < 4" type="primary" @click="nextWizard">下一步</el-button>
        <el-button
          v-else-if="userStore.hasPermission('resource:create')"
          type="primary"
          :loading="registering"
          @click="submitWizard"
        >确认注册</el-button>
      </template>
    </el-dialog>

    <!-- MCP 工作台 -->
    <el-dialog v-model="showProbe" title="MCP 连接工作台" width="820px" destroy-on-close @closed="clearProbeSecrets">
      <el-form label-width="120px">
        <el-form-item label="探测来源">
          <el-radio-group v-model="probeMode" @change="onProbeModeChange">
            <el-radio-button value="registered">已注册连接</el-radio-button>
            <el-radio-button value="remote">临时远程地址</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="probeMode === 'registered'" label="资源">
          <el-select v-model="probeForm.resource_id" filterable clearable style="width: 100%" placeholder="选择 MCP 资源">
            <el-option v-for="m in mcpOptions" :key="m.resource_id" :label="`${m.name} (${m.resource_id})`" :value="m.resource_id" />
          </el-select>
        </el-form-item>
        <template v-else>
          <el-form-item label="HTTP Endpoint">
            <el-input v-model="probeForm.endpoint" placeholder="https://mcp.example.com/rpc" clearable />
          </el-form-item>
          <el-form-item label="Token">
            <el-input v-model="probeForm.token" type="password" show-password placeholder="关闭面板后清除" />
          </el-form-item>
          <el-form-item label="Egress 白名单">
            <el-input v-model="probeForm.allowlistText" placeholder="host1,host2" />
          </el-form-item>
        </template>
      </el-form>

      <el-space wrap style="margin-bottom: 12px">
        <el-tag :type="mcpStates.connected ? 'success' : 'info'">1. 连接 {{ mcpStates.connected ? '成功' : '未验证' }}</el-tag>
        <el-tag :type="mcpStates.listed ? 'success' : 'info'">2. 工具目录 {{ mcpStates.listed ? '已发现' : '未拉取' }}</el-tag>
        <el-tag :type="mcpStates.called ? 'success' : 'info'">3. 工具调用 {{ mcpStates.called ? '成功' : '未测' }}</el-tag>
        <el-tag type="warning">list_changed / stdio：未支持</el-tag>
      </el-space>

      <el-space>
        <el-button :loading="probeLoading && probeAction === 'initialize'" @click="mcpStep('initialize')">验证连接</el-button>
        <el-button :loading="probeLoading && probeAction === 'tools/list'" @click="mcpStep('tools/list')">获取工具目录</el-button>
      </el-space>

      <el-table v-if="mcpTools.length" :data="mcpTools" size="small" style="margin-top: 12px" @row-click="pickMcpTool">
        <el-table-column prop="name" label="工具" min-width="140" />
        <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
      </el-table>

      <div v-if="selectedMcpTool" style="margin-top: 12px">
        <div class="panel-title">调用 {{ selectedMcpTool.name }}</div>
        <SchemaForm v-model="mcpCallArgs" :schema="selectedMcpTool.inputSchema || { type: 'object', properties: {} }" />
        <el-button type="primary" :loading="probeLoading && probeAction === 'tools/call'" @click="mcpCallSelected">测试调用</el-button>
      </div>

      <p v-if="lastProbeMeta" class="hint">目标：{{ lastProbeMeta.mode }} · {{ lastProbeMeta.target }} · {{ lastProbeMeta.probed_at }}</p>
      <el-input v-if="probeResultText" v-model="probeResultText" type="textarea" :rows="8" readonly class="probe-result" />
      <template #footer>
        <el-button @click="showProbe = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 批次（保留） -->
    <el-dialog v-model="showBatch" title="冻结批量快照" width="560px">
      <el-form label-width="110px">
        <el-form-item label="数据集">
          <ResourcePicker v-model="batchForm.dataset_id" kind="dataset" />
        </el-form-item>
        <el-form-item label="版本 ID"><el-input-number v-model="batchForm.version_id" :min="0" /></el-form-item>
        <el-form-item label="分片大小"><el-input-number v-model="batchForm.shard_size" :min="1" :max="500" /></el-form-item>
        <el-form-item label="Token 预算"><el-input-number v-model="batchForm.token_budget" :min="0" /></el-form-item>
      </el-form>
      <el-card v-if="batchInfo" shadow="never" class="batch-card">
        <p>batch={{ batchInfo.batch_id }} · 状态 <strong>{{ batchInfo.status }}</strong></p>
        <el-progress :percentage="batchInfo.progress || 0" />
      </el-card>
      <template #footer>
        <el-button @click="closeBatch">关闭</el-button>
        <el-button v-if="batchInfo?.batch_id" @click="refreshBatch">刷新</el-button>
        <el-button v-if="batchInfo?.batch_id && !['success','cancelled'].includes(batchInfo.status)" @click="cancelBatch">取消</el-button>
        <el-button type="primary" :loading="batchLoading" @click="runBatch">创建批次</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { resourcesApi, batchApi } from '@/api'
import { useUserStore } from '@/stores/user'
import StatusBadge from '@/components/StatusBadge.vue'
import SchemaForm from '@/components/SchemaForm.vue'
import ResourcePicker from '@/components/ResourcePicker.vue'

const userStore = useUserStore()
const route = useRoute()
const router = useRouter()

const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const search = ref('')
const statusFilter = ref('')
const tab = ref('all')
const versionsSupported = false

const showDetail = ref(false)
const detail = ref(null)

const showTrial = ref(false)
const trialRow = ref(null)
const trialMode = ref('form')
const trialBody = ref({})
const trialJsonText = ref('{}')
const trialSchema = ref({ type: 'object', properties: {} })
const trialLoading = ref(false)
const trialResult = ref(null)
const schemaFormRef = ref(null)

const showWizard = ref(false)
const wizardStep = ref(0)
const registering = ref(false)
const checking = ref(false)
const checkLog = ref('')
const checks = ref({ schema: false, connect: null })
const wizard = ref(emptyWizard())

const showProbe = ref(false)
const probeLoading = ref(false)
const probeAction = ref('')
const probeResultText = ref('')
const probeMode = ref('registered')
const lastProbeMeta = ref(null)
const mcpOptions = ref([])
const mcpTools = ref([])
const selectedMcpTool = ref(null)
const mcpCallArgs = ref({})
const mcpStates = ref({ connected: false, listed: false, called: false })
const probeForm = ref({
  resource_id: '',
  endpoint: '',
  token: '',
  allowlistText: '',
})

const showBatch = ref(false)
const batchLoading = ref(false)
const batchForm = ref({ dataset_id: null, version_id: 0, shard_size: 50, token_budget: 0 })
const batchInfo = ref(null)
let batchTimer

const kindIntro = computed(() => {
  if (wizard.value.kind === 'mcp') return '仅支持 HTTP JSON-RPC；stdio / list_changed 未实现，不可假装热更新。'
  if (wizard.value.kind === 'skill') return '仅可注册服务端已支持的 workflow Skill；code/agent 类型不可保存为可执行资源。'
  return '适合同步 Tool；副作用需在 Manifest 中声明，试用时会提示确认。'
})

const sideEffectHint = computed(() => {
  const se = trialRow.value?.manifest?.capabilities?.side_effects
  if (!se || se === 'none') return ''
  return `该资源声明副作用：${typeof se === 'string' ? se : JSON.stringify(se)}。将发起真实调用。`
})

function emptyWizard() {
  return {
    kind: 'tool',
    ns: 'demo',
    slug: '',
    name: '',
    description: '',
    version: '1.0.0',
    call_mode: 'sync',
    endpoint: '',
    token: '',
    allowlist: '',
    paramMode: 'form',
    fields: [
      { key: 'prediction', type: 'string', required: true },
      { key: 'reference', type: 'string', required: true },
    ],
    schemaJson: '',
    rawManifest: '',
  }
}

function pretty(v) {
  try {
    return JSON.stringify(v ?? {}, null, 2)
  } catch {
    return String(v)
  }
}

function healthPhase(h) {
  if (h === 'online') return 'completed'
  if (h === 'abnormal') return 'failed'
  return 'idle'
}

function inputSchema(row) {
  return row?.manifest?.capabilities?.input_schema || { type: 'object', properties: {} }
}

function typeFromTab(t) {
  if (t === 'all') return ''
  return t
}

async function loadData() {
  loading.value = true
  try {
    const res = await resourcesApi.list({
      page: page.value,
      page_size: pageSize.value,
      resource_type: typeFromTab(tab.value),
      status: statusFilter.value || undefined,
      search: search.value || undefined,
    })
    items.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

function reloadFirst() {
  page.value = 1
  loadData()
  syncRoute()
}

function onTabChange() {
  reloadFirst()
}

function syncRoute() {
  router.replace({
    path: '/resources',
    query: {
      tab: tab.value !== 'all' ? tab.value : undefined,
      resource: detail.value?.resource_id || route.query.resource || undefined,
      q: search.value || undefined,
      page: page.value > 1 ? String(page.value) : undefined,
    },
  })
}

async function openDetail(row) {
  if (!row) return
  try {
    detail.value = await resourcesApi.get(row.resource_id || row)
    showDetail.value = true
    syncRoute()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '加载详情失败')
  }
}

async function runHealth(row) {
  const res = await resourcesApi.health(row.resource_id)
  ElMessage[res.ok ? 'success' : 'warning'](res.detail || res.status)
  if (detail.value?.resource_id === row.resource_id) {
    detail.value = { ...detail.value, health_status: res.status || (res.ok ? 'online' : 'abnormal') }
  }
}

function openTrial(row) {
  trialRow.value = row
  trialSchema.value = inputSchema(row)
  const defaults = {}
  const propsMap = trialSchema.value.properties || {}
  for (const [k, def] of Object.entries(propsMap)) {
    if (def && def.default !== undefined) defaults[k] = def.default
  }
  if (row.resource_type === 'mcp') {
    trialBody.value = { method: 'initialize', id: 1, ...defaults }
  } else {
    trialBody.value = { ...defaults }
  }
  trialJsonText.value = pretty(trialBody.value)
  trialResult.value = null
  trialMode.value = Object.keys(propsMap).length ? 'form' : 'json'
  showTrial.value = true
}

function syncJsonToBody() {
  try {
    trialBody.value = JSON.parse(trialJsonText.value || '{}')
  } catch (e) {
    ElMessage.error(`JSON 无效：${e.message}`)
  }
}

watch(trialBody, (v) => {
  if (trialMode.value === 'form') trialJsonText.value = pretty(v)
}, { deep: true })

watch(trialMode, (mode) => {
  if (mode === 'json') trialJsonText.value = pretty(trialBody.value)
  if (mode === 'form') {
    try {
      trialBody.value = JSON.parse(trialJsonText.value || '{}')
    } catch { /* keep */ }
  }
})

async function runTrial() {
  if (!trialRow.value) return
  if (trialMode.value === 'json') {
    try {
      trialBody.value = JSON.parse(trialJsonText.value || '{}')
    } catch (e) {
      ElMessage.error(`JSON 无效，未发送：${e.message}`)
      return
    }
  } else if (schemaFormRef.value) {
    const v = schemaFormRef.value.validate()
    if (!v.ok) {
      ElMessage.error(`缺少必填：${v.missing.join(', ')}`)
      return
    }
  }
  if (sideEffectHint.value) {
    try {
      await ElMessageBox.confirm(sideEffectHint.value, '确认真实调用', { type: 'warning' })
    } catch {
      return
    }
  }
  trialLoading.value = true
  trialResult.value = null
  const started = performance.now()
  try {
    const res = await resourcesApi.invoke({
      resource_id: trialRow.value.resource_id,
      body: trialBody.value,
      correlation_id: `trial-${Date.now()}`,
    })
    const bodyStatus = res.body?.status || res.header?.status || ''
    const appFailed = ['failed', 'error', 'denied'].includes(String(bodyStatus).toLowerCase()) || res.body?.ok === false
    trialResult.value = {
      ok: !appFailed,
      statusText: appFailed ? `业务失败 (${bodyStatus || 'failed'})` : `业务状态 ${bodyStatus || 'success'}`,
      latency_ms: Math.round(performance.now() - started),
      error_code: res.body?.error_code || res.body?.result?.error || '',
      summary: res.body?.result ?? res.body,
      raw: res,
    }
    if (appFailed) ElMessage.error(trialResult.value.statusText)
    else ElMessage.success('调用已返回（请核对业务状态）')
  } catch (e) {
    trialResult.value = {
      ok: false,
      statusText: '请求失败',
      latency_ms: Math.round(performance.now() - started),
      error_code: e?.response?.status || '',
      summary: e?.response?.data || e?.message,
      raw: e?.response?.data || String(e),
    }
    ElMessage.error(String(e?.response?.data?.message || e?.message || e))
  } finally {
    trialLoading.value = false
  }
}

function copyTrial() {
  navigator.clipboard?.writeText(pretty(trialResult.value?.raw))
  ElMessage.success('已复制')
}

function onTrialClosed() {
  trialRow.value = null
  trialResult.value = null
}

function openWizard() {
  wizard.value = emptyWizard()
  wizardStep.value = 0
  checks.value = { schema: false, connect: null }
  checkLog.value = ''
  showWizard.value = true
}

function resetWizard() {
  wizard.value.token = ''
}

function schemaFromFields() {
  const properties = {}
  const required = []
  for (const f of wizard.value.fields) {
    if (!f.key) continue
    properties[f.key] = { type: f.type || 'string' }
    if (f.required) required.push(f.key)
  }
  return { type: 'object', properties, required }
}

function pullSchemaFromJson() {
  try {
    const s = JSON.parse(wizard.value.schemaJson || '{}')
    const props = s.properties || {}
    wizard.value.fields = Object.entries(props).map(([key, def]) => ({
      key,
      type: def.type === 'integer' ? 'number' : (def.type || 'string'),
      required: (s.required || []).includes(key),
    }))
  } catch {
    /* keep */
  }
}

function buildManifest() {
  if (wizard.value.rawManifest.trim()) {
    return JSON.parse(wizard.value.rawManifest)
  }
  const rid = `${wizard.value.ns}/${wizard.value.slug}`.toLowerCase()
  if (wizard.value.kind === 'mcp') {
    const interfaces = { endpoint: wizard.value.endpoint, method: 'POST', auth_type: wizard.value.token ? 'bearer' : 'none' }
    if (wizard.value.token) interfaces.auth = { token: wizard.value.token }
    if (wizard.value.allowlist.trim()) {
      interfaces.egress_allowlist = wizard.value.allowlist.split(',').map((s) => s.trim()).filter(Boolean)
    }
    return {
      spec_version: '0.6.1',
      resource_id: rid,
      resource_type: 'mcp',
      name: wizard.value.name,
      description: wizard.value.description,
      version: wizard.value.version,
      owner: { name: 'tenant', contact: 'n/a', email: 'n/a@local' },
      capabilities: {
        input_schema: { type: 'object', properties: { method: { type: 'string' }, params: { type: 'object' } } },
        output_schema: { type: 'object' },
        call_mode: 'sync',
        timeout: 30,
      },
      interfaces,
    }
  }
  const schema = wizard.value.paramMode === 'json' && wizard.value.schemaJson.trim()
    ? JSON.parse(wizard.value.schemaJson)
    : schemaFromFields()
  return {
    spec_version: '0.6.1',
    resource_id: rid,
    resource_type: wizard.value.kind,
    name: wizard.value.name,
    description: wizard.value.description,
    version: wizard.value.version,
    owner: { name: 'tenant', contact: 'n/a', email: 'n/a@local' },
    capabilities: {
      input_schema: schema,
      output_schema: { type: 'object' },
      call_mode: wizard.value.call_mode,
      timeout: 30,
      side_effects: 'none',
    },
    interfaces: {
      endpoint: wizard.value.kind === 'skill' ? `local://skill/${rid}` : `local://tool/${rid}`,
      method: 'exec',
      auth_type: 'none',
    },
  }
}

function nextWizard() {
  if (wizardStep.value === 0 && !wizard.value.kind) return
  if (wizardStep.value === 1) {
    if (!wizard.value.ns || !wizard.value.slug || !wizard.value.name) {
      ElMessage.warning('请填写命名空间、标识与名称')
      return
    }
  }
  if (wizardStep.value === 2) {
    if (wizard.value.paramMode === 'form') {
      wizard.value.schemaJson = pretty(schemaFromFields())
    }
    try {
      buildManifest()
    } catch (e) {
      ElMessage.error(`Manifest 无法构建：${e.message}`)
      return
    }
  }
  wizardStep.value += 1
}

async function runWizardChecks() {
  checking.value = true
  checkLog.value = ''
  checks.value = { schema: false, connect: null }
  try {
    const mf = buildManifest()
    checks.value.schema = !!(mf.resource_id && mf.name && mf.resource_type)
    checkLog.value += `结构检查：${checks.value.schema ? 'OK' : 'FAIL'}\n`
    if (wizard.value.kind === 'mcp' && wizard.value.endpoint) {
      try {
        const res = await resourcesApi.mcpProbe({
          endpoint: wizard.value.endpoint,
          token: wizard.value.token || '',
          method: 'initialize',
          egress_allowlist: wizard.value.allowlist
            ? wizard.value.allowlist.split(',').map((s) => s.trim()).filter(Boolean)
            : [],
        })
        checks.value.connect = !!res.ok
        checkLog.value += `连接探测：${checks.value.connect ? 'OK' : 'FAIL'} target=${res.target}\n`
      } catch (e) {
        checks.value.connect = false
        checkLog.value += `连接探测失败：${e?.response?.data?.message || e.message}\n`
      }
    } else {
      checkLog.value += '连接探测：非 MCP 或无 endpoint，跳过（保持未执行）\n'
    }
  } catch (e) {
    checkLog.value += String(e.message || e)
  } finally {
    checking.value = false
  }
}

async function submitWizard() {
  registering.value = true
  try {
    const mf = buildManifest()
    const res = await resourcesApi.register(mf)
    ElMessage.success('已注册')
    showWizard.value = false
    wizard.value.token = ''
    await loadData()
    openDetail(res)
    if (userStore.hasPermission('resource:invoke')) openTrial(res)
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '注册失败')
  } finally {
    registering.value = false
  }
}

function onProbeModeChange() {
  if (probeMode.value === 'registered') {
    probeForm.value.endpoint = ''
    probeForm.value.token = ''
    probeForm.value.allowlistText = ''
  } else {
    probeForm.value.resource_id = ''
  }
  resetMcpStates()
}

function resetMcpStates() {
  mcpStates.value = { connected: false, listed: false, called: false }
  mcpTools.value = []
  selectedMcpTool.value = null
  mcpCallArgs.value = {}
  probeResultText.value = ''
  lastProbeMeta.value = null
}

function clearProbeSecrets() {
  probeForm.value.token = ''
  resetMcpStates()
}

async function openMcpWorkbench(row) {
  resetMcpStates()
  const list = await resourcesApi.list({ resource_type: 'mcp', page_size: 100 })
  mcpOptions.value = list.items || []
  if (row?.resource_id) {
    probeMode.value = 'registered'
    probeForm.value.resource_id = row.resource_id
    probeForm.value.endpoint = ''
  } else if (!probeForm.value.resource_id && !probeForm.value.endpoint) {
    probeMode.value = 'remote'
  }
  showProbe.value = true
}

function probePayload(extra = {}) {
  return {
    resource_id: probeMode.value === 'registered' ? probeForm.value.resource_id.trim() : '',
    endpoint: probeMode.value === 'remote' ? probeForm.value.endpoint.trim() : '',
    token: probeMode.value === 'remote' ? (probeForm.value.token || '') : '',
    egress_allowlist:
      probeMode.value === 'remote' && probeForm.value.allowlistText.trim()
        ? probeForm.value.allowlistText.split(',').map((s) => s.trim()).filter(Boolean)
        : [],
    ...extra,
  }
}

async function mcpStep(method) {
  probeLoading.value = true
  probeAction.value = method
  try {
    const res = await resourcesApi.mcpProbe(probePayload({ method, params: {} }))
    lastProbeMeta.value = { mode: res.mode, target: res.target, probed_at: res.probed_at }
    probeResultText.value = pretty({ mode: res.mode, target: res.target, result: res.result })
    if (method === 'initialize') {
      mcpStates.value.connected = !!res.ok
      ElMessage.success('连接验证完成')
    }
    if (method === 'tools/list') {
      mcpStates.value.listed = true
      const tools = res.result?.result?.tools || res.result?.tools || []
      mcpTools.value = tools
      ElMessage.success(`发现 ${tools.length} 个工具`)
    }
  } catch (e) {
    const detail = e?.response?.data?.message || e?.message || e
    probeResultText.value = String(detail)
    ElMessage.error(String(detail))
    if (method === 'initialize') mcpStates.value.connected = false
  } finally {
    probeLoading.value = false
    probeAction.value = ''
  }
}

function pickMcpTool(row) {
  selectedMcpTool.value = row
  mcpCallArgs.value = {}
}

async function mcpCallSelected() {
  if (!selectedMcpTool.value) return
  probeLoading.value = true
  probeAction.value = 'tools/call'
  try {
    const res = await resourcesApi.mcpProbe(
      probePayload({
        method: 'tools/call',
        params: { name: selectedMcpTool.value.name, arguments: mcpCallArgs.value },
      }),
    )
    lastProbeMeta.value = { mode: res.mode, target: res.target, probed_at: res.probed_at }
    probeResultText.value = pretty({ mode: res.mode, target: res.target, result: res.result })
    mcpStates.value.called = !!res.ok
    ElMessage.success('工具调用已返回')
  } catch (e) {
    mcpStates.value.called = false
    const detail = e?.response?.data?.message || e?.message || e
    probeResultText.value = String(detail)
    ElMessage.error(String(detail))
  } finally {
    probeLoading.value = false
    probeAction.value = ''
  }
}

async function runBatch() {
  if (!batchForm.value.dataset_id) {
    ElMessage.warning('请选择数据集')
    return
  }
  batchLoading.value = true
  try {
    const payload = {
      dataset_id: batchForm.value.dataset_id,
      shard_size: batchForm.value.shard_size,
      token_budget: batchForm.value.token_budget || 0,
    }
    if (batchForm.value.version_id) payload.version_id = batchForm.value.version_id
    batchInfo.value = await batchApi.run(payload)
    ElMessage.success('已创建批次')
    startBatchPoll()
  } finally {
    batchLoading.value = false
  }
}

async function refreshBatch() {
  if (!batchInfo.value?.batch_id) return
  batchInfo.value = await batchApi.status(batchInfo.value.batch_id)
}

async function cancelBatch() {
  if (!batchInfo.value?.batch_id) return
  await batchApi.cancel(batchInfo.value.batch_id)
  await refreshBatch()
  ElMessage.success('已取消')
}

function startBatchPoll() {
  clearInterval(batchTimer)
  let inFlight = false
  const tick = async () => {
    if (!batchInfo.value?.batch_id || inFlight) return
    if (['success', 'cancelled', 'paused_budget', 'failed'].includes(batchInfo.value.status)) {
      clearInterval(batchTimer)
      batchTimer = null
      return
    }
    inFlight = true
    try {
      await refreshBatch()
    } finally {
      inFlight = false
    }
  }
  batchTimer = setInterval(tick, 3000)
}

function closeBatch() {
  clearInterval(batchTimer)
  showBatch.value = false
}

onMounted(async () => {
  if (route.query.tab) tab.value = String(route.query.tab)
  if (route.query.q) search.value = String(route.query.q)
  if (route.query.page) page.value = Number(route.query.page) || 1
  await loadData()
  if (route.query.resource) {
    try {
      await openDetail(String(route.query.resource))
    } catch { /* */ }
  }
})

onUnmounted(() => clearInterval(batchTimer))
</script>

<style scoped>
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.pager { display: flex; justify-content: flex-end; margin-top: 12px; }
.name-cell { display: flex; align-items: center; gap: 8px; }
.sub { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 2px; }
.hint { font-size: 12px; color: var(--el-text-color-secondary); }
.payload {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 280px;
  overflow: auto;
  background: #f8fafc;
  padding: 8px;
  border-radius: 8px;
}
.panel-title { font-weight: 600; margin-bottom: 8px; }
.drawer-actions { display: flex; gap: 8px; margin-top: 12px; }
.field-row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.batch-card { margin-top: 8px; font-size: 13px; }
.probe-result { margin-top: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
</style>
