<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">评测任务</h2>
        <p class="page-desc">队列调度、依赖编排与模板化评测。正式任务可走审核；试跑可直接执行。</p>
      </div>
      <el-button v-if="userStore.hasPermission('task:create')" type="primary" @click="openCreate()">创建任务</el-button>
    </div>
    <el-card>
      <div class="toolbar">
        <el-input v-model="search" placeholder="搜索任务名" clearable style="width: 220px" @clear="onFilter" @keyup.enter="onFilter" />
        <el-select v-model="statusFilter" placeholder="状态" clearable style="width: 150px" @change="onFilter">
          <el-option label="草稿" value="draft" />
          <el-option label="待审" value="pending_review" />
          <el-option label="排队" value="queued" />
          <el-option label="执行中" value="running" />
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
          <el-option label="已取消" value="cancelled" />
        </el-select>
        <el-button @click="onFilter">查询</el-button>
      </div>
      <PageAsyncState
        v-if="['loading', 'error', 'forbidden', 'uncreated'].includes(listState)"
        :state="listState"
        :errorMessage="loadError"
      />
      <template v-else>
      <el-table v-loading="loading" :data="items" stripe>
        <template #empty>
          <EmptyState type="task" action-text="创建任务" :show-action="userStore.hasPermission('task:create')" @action="openCreate" />
        </template>
        <el-table-column prop="name" label="名称" min-width="160">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/tasks/${row.id}`)">{{ row.name }}</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="task_type" label="类型" width="100" />
        <el-table-column prop="scene" label="场景" width="110" />
        <el-table-column prop="industry" label="行业" width="90" />
        <el-table-column prop="priority" label="优先级" width="80" />
        <el-table-column prop="status" label="状态" width="160">
          <template #default="{ row }">
            <StatusBadge :phase="taskPhase(row.status)" :text="statusText(row)" />
            <span v-if="row.attempt" class="muted"> ·#{{ row.attempt }}</span>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="140">
          <template #default="{ row }">
            <el-progress :percentage="row.progress || 0" :stroke-width="8" />
          </template>
        </el-table-column>
        <el-table-column prop="pass_rate" label="通过率" width="90">
          <template #default="{ row }">{{ formatRate(row.pass_rate) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="280">
          <template #default="{ row }">
            <el-button v-if="userStore.hasPermission('task:edit') && row.status === 'draft'" link type="primary" size="small" @click="submitReview(row)">提交审核</el-button>
            <el-button v-if="userStore.hasPermission('task:audit') && row.status === 'pending_review'" link type="primary" size="small" @click="audit(row, true)">通过</el-button>
            <el-button v-if="userStore.hasPermission('task:run') && !['running'].includes(row.status)" link type="primary" size="small" @click="run(row)">执行</el-button>
            <el-button v-if="userStore.hasPermission('task:run') && ['queued','running','draft','pending_review'].includes(row.status)" link size="small" @click="cancel(row)">取消</el-button>
            <el-button v-if="userStore.hasPermission('task:run') && ['success','failed','partial_failed','cancelled'].includes(row.status)" link type="warning" size="small" @click="retry(row)">重试</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager-line">第 {{ page }} 页 · 共 {{ total }} 条</div>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @current-change="loadData"
        @size-change="() => { page = 1; loadData() }"
      />
      </template>
    </el-card>

    <el-dialog v-model="showForm" title="创建评测任务" width="620px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="任务名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="任务模板">
          <el-select v-model="form.template_code" clearable filterable style="width: 100%" @change="applyTemplate">
            <el-option v-for="t in templates" :key="t.code" :label="t.name" :value="t.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.task_type">
            <el-option label="能力测试" value="capability" />
            <el-option label="安全可信" value="security" />
            <el-option label="场景应用" value="scene" />
            <el-option label="行业专项" value="industry" />
          </el-select>
        </el-form-item>
        <el-form-item label="场景">
          <el-select v-model="form.scene" filterable style="width: 100%">
            <el-option v-for="s in scenes" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="行业">
          <el-select v-model="form.industry" filterable style="width: 100%">
            <el-option v-for="s in industries" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级"><el-input-number v-model="form.priority" :min="1" :max="10" /></el-form-item>
        <el-form-item label="依赖任务">
          <el-select v-model="form.depends_on_id" clearable filterable remote :remote-method="searchDeps" style="width: 100%">
            <el-option v-for="t in depOptions" :key="t.id" :label="`${t.id} ${t.name}`" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="数据集">
          <ResourcePicker v-model="form.dataset_id" kind="dataset" placeholder="搜索数据集" @select="onDatasetSelect" />
        </el-form-item>
        <el-form-item label="被测模型">
          <ResourcePicker v-model="form.model_id" kind="model" placeholder="搜索模型" @select="onModelSelect" />
        </el-form-item>
        <el-form-item label="提示词">
          <el-select v-model="form.prompt_id" clearable filterable style="width: 100%">
            <el-option
              v-for="p in prompts"
              :key="p.id"
              :label="`${p.name} · ${p.status}`"
              :value="p.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="打分工具">
          <el-select v-model="form.judge_resource_id" style="width: 100%">
            <el-option v-for="r in judges" :key="r.resource_id" :label="r.name" :value="r.resource_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="仅测试">
          <el-switch v-model="form.trial_run" />
          <div class="hint">
            正式评测要求：数据集已发布且质检通过、提示词已发布、模型已配置 endpoint。不满足时请开启「仅测试」。
            <span v-if="gateHint" class="warn">{{ gateHint }}</span>
          </div>
        </el-form-item>
        <el-form-item label="Token 配额">
          <el-input-number v-model="form.token_quota" :min="0" />
          <span class="hint">0 表示不限制；耗尽后任务进入 paused_budget</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { promptsApi, resourcesApi, tasksApi } from '@/api'
import { useUserStore } from '@/stores/user'
import EmptyState from '@/components/EmptyState.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import ResourcePicker from '@/components/ResourcePicker.vue'
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
const search = ref(initialQuery.q)
const statusFilter = ref(initialQuery.status)
const showForm = ref(false)
const submitting = ref(false)
const prompts = ref([])
const judges = ref([])
const templates = ref([])
const scenes = ref([])
const industries = ref([])
const depOptions = ref([])
const selectedDataset = ref(null)
const selectedModel = ref(null)
const form = ref(emptyForm())
let pollTimer

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

function emptyForm() {
  return {
    name: '', task_type: 'capability', scene: 'chat', industry: 'general',
    dataset_id: null, model_id: null, prompt_id: null, judge_resource_id: 'builtin/exact_match',
    trial_run: false, template_code: '', priority: 5, depends_on_id: null, token_quota: 0
  }
}

function formatRate(v) {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

const STATUS_CN = {
  draft: '草稿',
  pending_review: '待审',
  queued: '排队',
  running: '执行中',
  success: '成功',
  failed: '失败',
  partial_failed: '部分失败',
  cancelled: '已取消',
  paused_budget: '预算暂停',
}

function taskPhase(st) {
  if (['queued', 'running'].includes(st)) return 'running'
  if (st === 'failed' || st === 'partial_failed') return 'failed'
  if (st === 'success') return 'completed'
  if (st === 'pending_review') return 'awaiting_approval'
  if (st === 'paused_budget') return 'budget_paused'
  if (st === 'draft') return 'idle'
  return 'idle'
}

function statusText(row) {
  const base = STATUS_CN[row.status] || row.status || ''
  const tags = []
  if (row.trial_run) tags.push('试跑')
  if (row.simulation) tags.push('模拟')
  if (row.cancel_requested && row.status === 'running') tags.push('取消中')
  return tags.length ? `${base}（${tags.join('/')}）` : base
}

const selectedPrompt = computed(() => prompts.value.find((p) => p.id === form.value.prompt_id))

const gateHint = computed(() => {
  if (form.value.trial_run) return ''
  const tips = []
  const ds = selectedDataset.value
  if (ds) {
    const st = ds.status || ds.publish_status || ''
    if (st !== 'published') tips.push('数据集未发布')
    if (!['passed', 'ok', 'good'].includes(ds.quality_status)) tips.push('数据集未质检通过')
  }
  const m = selectedModel.value
  if (m && !(m.api_url || '').trim()) tips.push('模型无 endpoint')
  const p = selectedPrompt.value
  if (p && p.status !== 'published') tips.push('提示词未发布')
  return tips.length ? `当前不满足正式评测：${tips.join('；')}。将自动建议开启仅测试。` : ''
})

function onDatasetSelect(opt) {
  selectedDataset.value = opt?.raw || null
  suggestTrial()
}
function onModelSelect(opt) {
  selectedModel.value = opt?.raw || null
  suggestTrial()
}
function suggestTrial() {
  if (gateHint.value && !form.value.trial_run) {
    form.value.trial_run = true
    ElMessage.info('已自动开启「仅测试」以满足门禁')
  }
}

function onFilter() {
  page.value = 1
  loadData()
}

async function persistQuery() {
  await writeListQuery(router, {
    page: page.value,
    page_size: pageSize.value,
    q: search.value,
    status: statusFilter.value,
  })
}

async function fetchList({ silent = false } = {}) {
  if (!silent) loading.value = true
  loadError.value = ''
  forbidden.value = false
  try {
    const res = await tasksApi.list({
      page: page.value,
      page_size: pageSize.value,
      search: search.value || undefined,
      status: statusFilter.value || undefined,
    })
    items.value = res.items || []
    total.value = res.total ?? items.value.length
    createdOnce.value = true
  } catch (e) {
    loadError.value = listErr(e, '任务列表加载失败')
    if (e?.response?.status === 403) forbidden.value = true
  } finally {
    if (!silent) loading.value = false
  }
}

async function loadData() {
  await persistQuery()
  await fetchList()
}

async function searchDeps(q) {
  const res = await tasksApi.list({ page: 1, page_size: 30, search: q || undefined })
  depOptions.value = res.items || []
}

function applyTemplate(code) {
  const t = templates.value.find((x) => x.code === code)
  if (!t) return
  form.value.task_type = t.task_type
  form.value.scene = t.scene
  form.value.industry = t.industry
  form.value.judge_resource_id = t.judge_resource_id
  if (t.pack_dataset_id) form.value.dataset_id = t.pack_dataset_id
  if (!form.value.name || form.value.name === '评测任务') form.value.name = t.name
}

async function openCreate(presetCode) {
  const [ps, rs, cat, tpls] = await Promise.all([
    promptsApi.list({ page_size: 100 }),
    resourcesApi.list({ resource_type: 'tool', page_size: 50 }),
    tasksApi.catalog(),
    tasksApi.templates()
  ])
  prompts.value = ps.items || []
  judges.value = rs.items || []
  scenes.value = cat.scenes || []
  industries.value = cat.industries || []
  templates.value = tpls.items || []
  selectedDataset.value = null
  selectedModel.value = null
  form.value = {
    ...emptyForm(),
    name: '评测任务',
    template_code: presetCode || route.query.template || ''
  }
  await searchDeps('')
  if (form.value.template_code) applyTemplate(form.value.template_code)
  suggestTrial()
  showForm.value = true
}

async function submit() {
  if (!form.value.trial_run && gateHint.value) {
    ElMessage.warning(gateHint.value)
    return
  }
  submitting.value = true
  try {
    const created = await tasksApi.create(form.value)
    ElMessage.success('已创建')
    showForm.value = false
    router.push(`/tasks/${created.id}`)
  } finally {
    submitting.value = false
  }
}

async function run(row) {
  await tasksApi.run(row.id)
  ElMessage.success('已提交执行')
  loadData()
}

async function cancel(row) {
  await tasksApi.cancel(row.id)
  ElMessage.success('已请求取消')
  loadData()
}

async function retry(row) {
  await tasksApi.retry(row.id)
  ElMessage.success('已重试入队')
  loadData()
}

async function submitReview(row) {
  await tasksApi.submit(row.id)
  ElMessage.success('已提交审核')
  loadData()
}

async function audit(row, approved) {
  await tasksApi.audit(row.id, { approved })
  ElMessage.success(approved ? '已通过' : '已退回')
  loadData()
}

watch(() => route.query, () => {
  const next = readListQuery(route.query)
  if (
    next.page === page.value
    && next.page_size === pageSize.value
    && next.q === search.value
    && next.status === statusFilter.value
  ) return
  page.value = next.page
  pageSize.value = next.page_size
  search.value = next.q
  statusFilter.value = next.status
  fetchList()
})

onMounted(async () => {
  await loadData()
  pollTimer = setInterval(() => {
    const busy = items.value.some((x) => ['queued', 'running'].includes(x.status))
    if (busy) fetchList({ silent: true })
  }, 3000)
  if (route.query.template) openCreate(route.query.template)
})
onUnmounted(() => clearInterval(pollTimer))
</script>

<style scoped>
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.pagination { margin-top: 16px; justify-content: flex-end; }
.pager-line { margin-top: 12px; font-size: 13px; color: var(--text-secondary); }
.hint { margin-left: 8px; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.5; }
.warn { display: block; margin-top: 4px; color: var(--el-color-warning); }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
</style>
