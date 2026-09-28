<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">工具底座</h2>
        <p class="page-desc">Manifest 注册；Skill workflow `$ref`；MCP HTTP 探测；副作用 stub / egress allowlist。</p>
      </div>
      <el-button v-if="userStore.hasPermission('resource:invoke')" @click="showBatch = true">冻结批次</el-button>
      <el-button v-if="userStore.hasPermission('resource:invoke')" @click="openProbe()">MCP 探测</el-button>
      <el-button v-if="userStore.hasPermission('resource:create')" type="primary" @click="showReg = true">注册 Manifest</el-button>
    </div>
    <el-card>
      <div class="toolbar">
        <el-select v-model="resourceType" placeholder="类型" clearable style="width: 160px">
          <el-option label="Tool" value="tool" />
          <el-option label="DataSource" value="datasource" />
          <el-option label="Model" value="model" />
          <el-option label="Skill" value="skill" />
          <el-option label="MCP" value="mcp" />
          <el-option label="Agent" value="agent" />
        </el-select>
      </div>
      <el-table v-loading="loading" :data="items" stripe>
        <el-table-column prop="resource_id" label="资源 ID" min-width="180" />
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="resource_type" label="类型" width="110" />
        <el-table-column prop="version" label="版本" width="90" />
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column prop="call_count" label="调用" width="80" />
        <el-table-column label="操作" width="260">
          <template #default="{ row }">
            <el-button v-if="['tool','skill','mcp'].includes(row.resource_type) && userStore.hasPermission('resource:invoke')" link type="primary" size="small" @click="tryInvoke(row)">试调用</el-button>
            <el-button v-if="row.resource_type === 'mcp' && userStore.hasPermission('resource:invoke')" link type="primary" size="small" @click="openProbe(row)">探测</el-button>
            <el-button v-if="userStore.hasPermission('resource:view')" link type="primary" size="small" @click="health(row)">健康</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showBatch" title="冻结批量快照" width="560px">
      <el-form label-width="110px">
        <el-form-item label="数据集 ID"><el-input-number v-model="batchForm.dataset_id" :min="1" /></el-form-item>
        <el-form-item label="版本 ID"><el-input-number v-model="batchForm.version_id" :min="0" placeholder="0=当前" /></el-form-item>
        <el-form-item label="分片大小"><el-input-number v-model="batchForm.shard_size" :min="1" :max="500" /></el-form-item>
        <el-form-item label="Token 预算"><el-input-number v-model="batchForm.token_budget" :min="0" /></el-form-item>
      </el-form>
      <el-card v-if="batchInfo" shadow="never" class="batch-card">
        <p>batch={{ batchInfo.batch_id }}</p>
        <p>snapshot={{ batchInfo.snapshot_id }} · 条数={{ batchInfo.item_count }} · 分片={{ batchInfo.shard_count }}</p>
        <p>
          状态 <strong>{{ batchInfo.status }}</strong>
          · 进度 {{ batchInfo.progress || 0 }}%
          · used {{ batchInfo.tokens_used || 0 }}/{{ batchInfo.token_budget || 0 }}
          <span v-if="batchInfo.error_code"> · {{ batchInfo.error_code }}</span>
        </p>
        <el-progress :percentage="batchInfo.progress || 0" :status="batchInfo.status === 'paused_budget' ? 'warning' : undefined" />
      </el-card>
      <template #footer>
        <el-button @click="closeBatch">关闭</el-button>
        <el-button v-if="batchInfo?.batch_id" @click="refreshBatch">刷新状态</el-button>
        <el-button v-if="batchInfo?.batch_id && !['success','cancelled'].includes(batchInfo.status)" @click="cancelBatch">取消</el-button>
        <el-button type="primary" :loading="batchLoading" @click="runBatch">创建批次</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showReg" title="注册 Manifest" width="720px">
      <el-input v-model="manifestText" type="textarea" rows="16" placeholder="粘贴 manifest.json" />
      <template #footer>
        <el-button @click="showReg = false">取消</el-button>
        <el-button type="primary" @click="register">提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showProbe" title="MCP 探测" width="720px">
      <el-form label-width="120px">
        <el-form-item label="资源 ID">
          <el-input v-model="probeForm.resource_id" placeholder="如 builtin/mcp_gateway；与 endpoint 二选一" clearable />
        </el-form-item>
        <el-form-item label="HTTP Endpoint">
          <el-input v-model="probeForm.endpoint" placeholder="https://mcp.example.com/rpc" clearable />
        </el-form-item>
        <el-form-item label="Token">
          <el-input v-model="probeForm.token" type="password" show-password placeholder="可选 Bearer" />
        </el-form-item>
        <el-form-item label="Egress 白名单">
          <el-input v-model="probeForm.allowlistText" placeholder="逗号分隔 host，如 mcp.example.com" />
        </el-form-item>
        <el-form-item label="方法">
          <el-select v-model="probeForm.method" style="width: 240px">
            <el-option label="initialize" value="initialize" />
            <el-option label="tools/list" value="tools/list" />
            <el-option label="tools/call" value="tools/call" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="probeForm.method === 'tools/call'" label="Call Params">
          <el-input v-model="probeForm.paramsText" type="textarea" rows="4" placeholder='{"name":"tool","arguments":{}}' />
        </el-form-item>
      </el-form>
      <el-input v-if="probeResultText" v-model="probeResultText" type="textarea" rows="10" readonly class="probe-result" />
      <template #footer>
        <el-button @click="showProbe = false">关闭</el-button>
        <el-button type="primary" :loading="probeLoading" @click="runProbe">探测</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { resourcesApi, batchApi } from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const loading = ref(false)
const items = ref([])
const resourceType = ref('')
const showReg = ref(false)
const manifestText = ref('')
const showBatch = ref(false)
const batchLoading = ref(false)
const batchForm = ref({ dataset_id: 1, version_id: 0, shard_size: 50, token_budget: 0 })
const batchInfo = ref(null)
let batchTimer

const showProbe = ref(false)
const probeLoading = ref(false)
const probeResultText = ref('')
const probeForm = ref({
  resource_id: '',
  endpoint: '',
  token: '',
  allowlistText: '',
  method: 'initialize',
  paramsText: '{"name":"builtin/exact_match","arguments":{"prediction":"北京","reference":"北京"}}',
})

async function loadData() {
  loading.value = true
  try {
    const res = await resourcesApi.list({ resource_type: resourceType.value, page_size: 100 })
    items.value = res.items || []
  } finally {
    loading.value = false
  }
}

async function register() {
  const manifest = JSON.parse(manifestText.value)
  await resourcesApi.register(manifest)
  ElMessage.success('注册成功')
  showReg.value = false
  loadData()
}

async function tryInvoke(row) {
  let body = { prediction: '北京', reference: '北京' }
  if (row.resource_type === 'mcp') {
    body = { method: 'initialize', id: 1 }
  } else if (row.resource_type === 'skill') {
    body = { prediction: '北京', reference: '北京' }
  }
  const res = await resourcesApi.invoke({ resource_id: row.resource_id, body })
  ElMessage.success(`status=${res.body?.status || res.header?.status || 'ok'}`)
}

function openProbe(row) {
  probeResultText.value = ''
  probeForm.value = {
    resource_id: row?.resource_id || 'builtin/mcp_gateway',
    endpoint: '',
    token: '',
    allowlistText: '',
    method: 'initialize',
    paramsText: '{"name":"builtin/exact_match","arguments":{"prediction":"北京","reference":"北京"}}',
  }
  showProbe.value = true
}

async function runProbe() {
  probeLoading.value = true
  probeResultText.value = ''
  try {
    const payload = {
      resource_id: probeForm.value.resource_id || '',
      endpoint: probeForm.value.endpoint || '',
      token: probeForm.value.token || '',
      method: probeForm.value.method,
      params: {},
      egress_allowlist: [],
    }
    if (probeForm.value.allowlistText.trim()) {
      payload.egress_allowlist = probeForm.value.allowlistText.split(',').map((s) => s.trim()).filter(Boolean)
    }
    if (probeForm.value.method === 'tools/call' && probeForm.value.paramsText.trim()) {
      payload.params = JSON.parse(probeForm.value.paramsText)
    }
    const res = await resourcesApi.mcpProbe(payload)
    probeResultText.value = JSON.stringify(res.result ?? res, null, 2)
    ElMessage.success('探测完成')
  } catch (e) {
    probeResultText.value = String(e?.response?.data?.message || e?.message || e)
  } finally {
    probeLoading.value = false
  }
}

async function health(row) {
  const res = await resourcesApi.health(row.resource_id)
  ElMessage[res.ok ? 'success' : 'warning'](res.detail || res.status)
}

async function runBatch() {
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
  batchTimer = setInterval(async () => {
    if (!batchInfo.value?.batch_id) return
    if (['success', 'cancelled', 'paused_budget', 'failed'].includes(batchInfo.value.status)) {
      clearInterval(batchTimer)
      return
    }
    await refreshBatch()
  }, 3000)
}

function closeBatch() {
  clearInterval(batchTimer)
  showBatch.value = false
}

watch(resourceType, loadData)
onMounted(loadData)
onUnmounted(() => clearInterval(batchTimer))
</script>

<style scoped>
.batch-card { margin-top: 8px; font-size: 13px; line-height: 1.6; }
.batch-card p { margin: 0 0 6px; }
.probe-result { margin-top: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
</style>
