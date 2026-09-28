<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">评测服务</h2>
        <p class="page-desc">报价版本快照 → 审批执行 → 有报告才可交付（幂等结算）→ 影子灰度四门禁后转正/回滚。</p>
      </div>
      <el-button v-if="userStore.hasPermission('service:create')" type="primary" @click="openCreate">提交需求</el-button>
    </div>
    <el-row :gutter="12" class="kanban">
      <el-col v-for="(n, k) in buckets" :key="k" :span="4">
        <el-card shadow="never" class="k-card">
          <div class="k-label">{{ k }}</div>
          <div class="k-val">{{ n }}</div>
        </el-card>
      </el-col>
    </el-row>
    <el-card>
      <el-table v-loading="loading" :data="items" stripe>
        <el-table-column prop="title" label="标题" min-width="140" />
        <el-table-column prop="industry" label="行业" width="90" />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="报价" width="120">
          <template #default="{ row }">
            <div>{{ row.quote_amount }}</div>
            <div class="sub">{{ row.quote_version || '—' }} · {{ row.quote_mode }}</div>
          </template>
        </el-table-column>
        <el-table-column label="灰度" min-width="160">
          <template #default="{ row }">
            <div>prod {{ row.production_version || 'v1' }}</div>
            <div class="sub">gray {{ row.gray_version || '—' }} · {{ Math.round((row.traffic_pct || 0) * 100) }}%</div>
            <el-tag v-if="row.shadow?.status" size="small" :type="row.shadow.status === 'ready' ? 'success' : row.shadow.status === 'inconclusive' ? 'warning' : 'info'">
              {{ row.shadow.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结算" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.delivery_settled ? 'success' : 'info'">{{ row.delivery_settled ? '已结' : '未结' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="report_summary" label="交付摘要" min-width="140" show-overflow-tooltip />
        <el-table-column v-if="userStore.hasPermission('service:edit')" label="办理" width="560">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="quote(row, 'auto')">自动报价</el-button>
            <el-button link type="primary" size="small" @click="quote(row, 'expert')">专家报价</el-button>
            <el-button link type="primary" size="small" @click="confirm(row)">确认</el-button>
            <el-button link type="primary" size="small" @click="setStatus(row, 'running')">执行</el-button>
            <el-button link type="success" size="small" @click="setStatus(row, 'delivered')">交付</el-button>
            <el-button v-if="row.task_id || row.report_path" link size="small" @click="download(row, 'json')">JSON</el-button>
            <el-button link size="small" @click="shadow(row)">影子</el-button>
            <el-button link size="small" @click="promote(row)">转正</el-button>
            <el-button link size="small" @click="rollback(row)">回滚</el-button>
            <el-button link size="small" @click="showShadow(row)">门禁</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showForm" title="提交评测需求" width="560px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="标题"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="行业"><el-input v-model="form.industry" /></el-form-item>
        <el-form-item label="工作空间">
          <el-select v-model="form.workspace_id" style="width: 100%">
            <el-option v-for="w in workspaces" :key="w.id" :label="`${w.name} (${w.used_tokens}/${w.quota_tokens})`" :value="w.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="需求"><el-input v-model="form.requirement" type="textarea" rows="4" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" @click="submit">提交</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="gateDrawer" title="影子门禁详情" size="420px">
      <template v-if="gateRow">
        <p>返回始终为 production；candidate 失败不影响生产。</p>
        <p>流量 {{ Math.round((gateRow.traffic_pct || 0) * 100) }}% · 证据 {{ gateRow.shadow?.evidence_days ?? 0 }} / {{ gateRow.shadow?.evidence_required_days || 7 }} 天</p>
        <el-table :data="gateRow.shadow?.gates || []" size="small">
          <el-table-column prop="code" label="门禁" />
          <el-table-column label="结果" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="row.ok ? 'success' : 'danger'">{{ row.ok ? '通过' : '未过' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="detail" label="详情" />
        </el-table>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { servicesApi } from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const loading = ref(false)
const items = ref([])
const workspaces = ref([])
const buckets = ref({})
const showForm = ref(false)
const gateDrawer = ref(false)
const gateRow = ref(null)
const form = ref({ title: '', industry: 'general', requirement: '', workspace_id: null })

function statusType(s) {
  if (s === 'delivered') return 'success'
  if (s === 'rejected') return 'danger'
  if (s === 'running') return 'warning'
  return 'info'
}

async function loadData() {
  loading.value = true
  try {
    const [res, kb, ws] = await Promise.all([
      servicesApi.list({ page_size: 50 }),
      servicesApi.kanban(),
      servicesApi.workspaces()
    ])
    items.value = res.items || []
    buckets.value = kb.buckets || {}
    workspaces.value = ws.items || []
    if (!form.value.workspace_id) form.value.workspace_id = workspaces.value[0]?.id
  } finally {
    loading.value = false
  }
}

function openCreate() {
  showForm.value = true
}

async function submit() {
  await servicesApi.create(form.value)
  ElMessage.success('已提交并生成自动报价版本')
  showForm.value = false
  loadData()
}

async function quote(row, mode) {
  let amount
  if (mode === 'expert') {
    const { value } = await ElMessageBox.prompt('专家报价金额', '报价', { inputValue: String(row.quote_amount || 800) })
    amount = Number(value)
  }
  await servicesApi.quote(row.id, { mode, amount })
  loadData()
}

async function confirm(row) {
  await servicesApi.confirm(row.id)
  ElMessage.success('已确认')
  loadData()
}

async function setStatus(row, status) {
  try {
    await servicesApi.updateStatus(row.id, { status })
    ElMessage.success(status === 'delivered' ? '已交付（幂等结算）' : '状态已更新')
    loadData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '更新失败')
  }
}

async function download(row, fmt = 'json') {
  const blob = await servicesApi.report(row.id, { fmt })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `service-${row.id}.${fmt}`
  a.click()
  URL.revokeObjectURL(url)
}

async function shadow(row) {
  await servicesApi.shadow(row.id, {
    gray_version: 'v-next',
    traffic_pct: 0.05,
    production: { score: 0.9, latency_ms: 100, samples: [0.9, 0.91, 0.89] },
    candidate: { score: 0.91, latency_ms: 105, samples: [0.91, 0.92, 0.9] }
  })
  ElMessage.success('影子双路已记录（仅返回生产结果，流量 5%）')
  loadData()
}

async function promote(row) {
  try {
    await servicesApi.promote(row.id)
    ElMessage.success('已转正')
    loadData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '转正失败')
  }
}

async function rollback(row) {
  await servicesApi.rollback(row.id)
  ElMessage.success('已回滚至 previous_stable，候选流量关闭')
  loadData()
}

function showShadow(row) {
  gateRow.value = row
  gateDrawer.value = true
}

onMounted(loadData)
</script>

<style scoped>
.kanban { margin-bottom: 12px; }
.k-card { border-radius: 12px; }
.k-label { color: var(--text-secondary); font-size: 12px; text-transform: lowercase; }
.k-val { font-size: 22px; font-weight: 600; margin-top: 4px; color: var(--text-primary); }
.sub { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
</style>
