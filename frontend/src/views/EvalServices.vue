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
      <PageAsyncState
        v-if="['loading', 'error', 'forbidden', 'uncreated'].includes(listState)"
        :state="listState"
        :errorMessage="loadError"
      />
      <template v-else>
      <el-table v-loading="loading" :data="items" stripe>
        <template #empty>
          <EmptyState type="default" title="暂无评测服务需求" description="提交需求后在此办理报价、执行与交付" action-text="提交需求" :show-action="userStore.hasPermission('service:create')" @action="openCreate" />
        </template>
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
        <el-table-column v-if="userStore.hasPermission('service:edit')" label="办理" width="220">
          <template #default="{ row }">
            <el-button
              v-for="a in primaryActions(row)"
              :key="a.key"
              link
              :type="a.type || 'primary'"
              size="small"
              @click="a.run"
            >{{ a.label }}</el-button>
            <el-dropdown v-if="moreActions(row).length" trigger="click">
              <el-button link size="small">更多</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="a in moreActions(row)"
                    :key="a.key"
                    @click="a.run"
                  >{{ a.label }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager-line">第 {{ page }} 页 · 共 {{ total }} 条</div>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @change="loadData"
      />
      </template>
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
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { servicesApi } from '@/api'
import { useUserStore } from '@/stores/user'
import EmptyState from '@/components/EmptyState.vue'
import PageAsyncState from '@/components/PageAsyncState.vue'
import { deriveAsyncState } from '@/utils/asyncState.js'
import { readListQuery, writeListQuery } from '@/utils/listQuery.js'

const userStore = useUserStore()
const router = useRouter()
const route = useRoute()
const initialQuery = readListQuery(route.query)
const loading = ref(false)
const loadError = ref('')
const createdOnce = ref(false)
const forbidden = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(initialQuery.page)
const pageSize = ref(initialQuery.page_size)
const workspaces = ref([])
const buckets = ref({})
const showForm = ref(false)
const gateDrawer = ref(false)
const gateRow = ref(null)
const form = ref({ title: '', industry: 'general', requirement: '', workspace_id: null })

const listState = computed(() => deriveAsyncState({
  loading: loading.value && !createdOnce.value,
  error: loadError.value,
  forbidden: forbidden.value,
  items: items.value,
  createdOnce: createdOnce.value,
}))

function listErr(e, fallback) {
  const d = e?.response?.data
  const msg = d?.message || d?.detail || e?.message
  return typeof msg === 'string' && msg ? msg : fallback
}

function statusType(s) {
  if (s === 'delivered') return 'success'
  if (s === 'rejected') return 'danger'
  if (s === 'running') return 'warning'
  return 'info'
}

function primaryActions(row) {
  const st = row.status
  const list = []
  if (['draft', 'submitted', 'quoted'].includes(st)) {
    list.push({ key: 'quote-auto', label: '自动报价', run: () => quote(row, 'auto') })
    list.push({ key: 'confirm', label: '确认', run: () => confirm(row) })
  } else if (st === 'confirmed') {
    list.push({ key: 'run', label: '执行', run: () => setStatus(row, 'running') })
  } else if (st === 'running') {
    list.push({ key: 'deliver', label: '交付', type: 'success', run: () => setStatus(row, 'delivered') })
    list.push({ key: 'gate', label: '门禁', run: () => showShadow(row) })
  } else if (st === 'delivered') {
    list.push({ key: 'gate', label: '门禁', run: () => showShadow(row) })
    if (row.shadow?.status === 'ready') {
      list.push({ key: 'promote', label: '转正', run: () => promote(row) })
    }
  } else {
    list.push({ key: 'gate', label: '门禁', run: () => showShadow(row) })
  }
  return list.slice(0, 2)
}

function moreActions(row) {
  const all = [
    { key: 'quote-expert', label: '专家报价', run: () => quote(row, 'expert') },
    { key: 'quote-auto', label: '自动报价', run: () => quote(row, 'auto') },
    { key: 'confirm', label: '确认', run: () => confirm(row) },
    { key: 'run', label: '执行', run: () => setStatus(row, 'running') },
    { key: 'deliver', label: '交付', run: () => setStatus(row, 'delivered') },
    { key: 'shadow', label: '影子采样', run: () => shadow(row) },
    { key: 'promote', label: '转正', run: () => promote(row) },
    { key: 'rollback', label: '回滚', run: () => rollback(row) },
    { key: 'gate', label: '门禁详情', run: () => showShadow(row) },
  ]
  if (row.task_id || row.report_path) {
    all.push({ key: 'json', label: '下载 JSON', run: () => download(row, 'json') })
  }
  const primaryKeys = new Set(primaryActions(row).map((a) => a.key))
  return all.filter((a) => !primaryKeys.has(a.key))
}

async function persistQuery() {
  await writeListQuery(router, {
    page: page.value,
    page_size: pageSize.value,
    q: '',
    status: '',
  })
}

async function loadData() {
  await persistQuery()
  loading.value = true
  loadError.value = ''
  forbidden.value = false
  try {
    const [res, kb, ws] = await Promise.all([
      servicesApi.list({ page: page.value, page_size: pageSize.value }),
      servicesApi.kanban(),
      servicesApi.workspaces()
    ])
    items.value = res.items || []
    total.value = res.total || 0
    buckets.value = kb.buckets || {}
    workspaces.value = ws.items || []
    if (!form.value.workspace_id) form.value.workspace_id = workspaces.value[0]?.id
    createdOnce.value = true
  } catch (e) {
    loadError.value = listErr(e, '评测服务列表加载失败')
    if (e?.response?.status === 403) forbidden.value = true
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
    traffic_pct: 0.05
  })
  ElMessage.success('已触发服务端影子采样（不提交客户端分数）')
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
watch(() => route.query, () => {
  const next = readListQuery(route.query)
  if (next.page === page.value && next.page_size === pageSize.value) return
  page.value = next.page
  pageSize.value = next.page_size
  loadData()
})
</script>

<style scoped>
.kanban { margin-bottom: 12px; }
.k-card { border-radius: 12px; }
.k-label { color: var(--text-secondary); font-size: 12px; text-transform: lowercase; }
.k-val { font-size: 22px; font-weight: 600; margin-top: 4px; color: var(--text-primary); }
.sub { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
.pagination { margin-top: 16px; justify-content: flex-end; }
.pager-line { margin-top: 12px; font-size: 13px; color: var(--text-secondary); }
</style>
