<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">{{ task.name || '任务详情' }}</h2>
        <p class="page-desc">{{ task.report_summary || '提交后将按数据分片逐条调用模型与打分工具；进度实时提交可见。' }}</p>
      </div>
      <div class="ops">
        <el-button @click="goBack">返回</el-button>
        <el-button v-if="userStore.hasPermission('task:run')" type="primary" :disabled="task.status === 'running'" @click="run">执行</el-button>
        <el-button
          v-if="userStore.hasPermission('task:run') && ['queued', 'running'].includes(task.status)"
          @click="cancel"
        >取消</el-button>
        <el-button
          v-if="userStore.hasPermission('task:run') && ['success', 'failed', 'partial_failed', 'cancelled'].includes(task.status)"
          type="warning"
          @click="retry"
        >重试</el-button>
        <el-button v-if="task.report_path" @click="download('json')">JSON</el-button>
        <el-button v-if="task.report_path" @click="download('xlsx')">Excel</el-button>
        <el-button v-if="task.report_path" @click="download('docx')">Word</el-button>
        <el-button v-if="task.report_path" @click="download('pdf')">PDF</el-button>
        <el-button v-if="userStore.hasPermission('task:edit')" @click="renderReport">重渲染报告</el-button>
      </div>
    </div>
    <PageAsyncState
      v-if="['loading', 'error', 'forbidden', 'uncreated'].includes(pageState)"
      :state="pageState"
      :errorMessage="loadError"
    />
    <template v-else>
    <el-card v-if="reportStatus" class="block report-panel">
      <template #header>
        <div class="report-head">
          <span>报告格式状态</span>
          <el-tag size="small" :type="reportJobStatusType">{{ reportStatus.job?.status || 'filesystem' }}</el-tag>
        </div>
      </template>
      <div class="fmt-grid">
        <button
          v-for="(meta, fmt) in reportStatus.formats || {}"
          :key="fmt"
          type="button"
          class="fmt-chip"
          :class="meta.status"
          :disabled="meta.status !== 'ready'"
          @click="download(fmt)"
        >
          <strong>{{ fmt }}</strong>
          <span>{{ meta.status }}</span>
          <em v-if="meta.error">{{ meta.error }}</em>
        </button>
      </div>
      <p v-if="(reportStatus.job?.evidence || []).length" class="evidence-hint">
        证据 {{ (reportStatus.job.evidence || []).slice(0, 3).map((e) => e.evidence_id).join(' · ') }}
      </p>
    </el-card>
    <el-row :gutter="16" class="block">
      <el-col :span="6"><el-card><div class="stat-label">状态</div><div class="stat-value">{{ statusLabel }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="stat-label">进度</div><div class="stat-value">{{ task.progress || 0 }}%</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="stat-label">通过率</div><div class="stat-value">{{ task.pass_rate == null ? '—' : `${(task.pass_rate * 100).toFixed(1)}%` }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="stat-label">平均分</div><div class="stat-value">{{ task.avg_score == null ? '—' : Number(task.avg_score).toFixed(3) }}</div></el-card></el-col>
    </el-row>
    <el-descriptions :column="3" border class="block">
      <el-descriptions-item label="模板">{{ task.template_code || '-' }}</el-descriptions-item>
      <el-descriptions-item label="场景">{{ task.scene }}</el-descriptions-item>
      <el-descriptions-item label="行业">{{ task.industry }}</el-descriptions-item>
      <el-descriptions-item label="优先级">{{ task.priority }}</el-descriptions-item>
      <el-descriptions-item label="依赖">{{ task.depends_on_id || '-' }}</el-descriptions-item>
      <el-descriptions-item label="尝试次数">{{ task.attempt || 0 }}</el-descriptions-item>
      <el-descriptions-item label="Token 配额">{{ task.token_quota || 0 }}</el-descriptions-item>
      <el-descriptions-item label="已用 Token">{{ task.tokens_used || 0 }}</el-descriptions-item>
      <el-descriptions-item label="预算状态">{{ budgetLabel }}</el-descriptions-item>
      <el-descriptions-item label="batch">{{ task.batch_id || '-' }}</el-descriptions-item>
      <el-descriptions-item label="snapshot">{{ task.snapshot_id || '-' }}</el-descriptions-item>
      <el-descriptions-item label="Lease">{{ task.lease_owner || '-' }}</el-descriptions-item>
      <el-descriptions-item label="Fencing">{{ task.fencing_token || '-' }}</el-descriptions-item>
      <el-descriptions-item label="工具版本">{{ task.tool_version || '-' }}</el-descriptions-item>
      <el-descriptions-item label="血缘 checksum">{{ lineage.checksum || '-' }}</el-descriptions-item>
      <el-descriptions-item label="通道">{{ lineage.channel_type || '-' }}</el-descriptions-item>
      <el-descriptions-item label="trace">{{ lineage.trace_id || '-' }}</el-descriptions-item>
    </el-descriptions>
    <el-card class="block">
      <template #header>子任务分片</template>
      <el-table :data="subtasks" stripe size="small">
        <el-table-column prop="shard_no" label="分片" width="80" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column label="样本" width="140">
          <template #default="{ row }">{{ row.item_from }} - {{ row.item_to }}</template>
        </el-table-column>
        <el-table-column prop="progress" label="进度" width="80" />
      </el-table>
    </el-card>
    <el-card class="block">
      <template #header>事件</template>
      <el-timeline>
        <el-timeline-item v-for="e in events" :key="e.id" :timestamp="e.created_at">
          {{ e.event_type }}
        </el-timeline-item>
      </el-timeline>
    </el-card>
    <el-card>
      <template #header>逐条结果（{{ results.length }}）</template>
      <el-table :data="results" stripe>
        <el-table-column prop="item_no" label="#" width="60" />
        <el-table-column prop="input_content" label="输入" min-width="160" show-overflow-tooltip />
        <el-table-column prop="model_output" label="模型输出" min-width="160" show-overflow-tooltip />
        <el-table-column prop="reference_answer" label="参考" min-width="120" show-overflow-tooltip />
        <el-table-column prop="score" label="得分" width="80" />
        <el-table-column prop="passed" label="通过" width="70">
          <template #default="{ row }">{{ row.passed ? '是' : '否' }}</template>
        </el-table-column>
        <el-table-column prop="execution_status" label="执行" width="100" />
        <el-table-column prop="score_status" label="打分" width="100" />
      </el-table>
      <div class="pager-line">第 {{ resultsPage }} 页 · 共 {{ resultsTotal }} 条</div>
      <el-pagination
        v-model:current-page="resultsPage"
        v-model:page-size="resultsPageSize"
        :total="resultsTotal"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @change="load"
      />
    </el-card>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { tasksApi } from '@/api'
import { useUserStore } from '@/stores/user'
import PageAsyncState from '@/components/PageAsyncState.vue'
import { deriveAsyncState } from '@/utils/asyncState.js'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const loadError = ref('')
const createdOnce = ref(false)
const task = ref({})
const results = ref([])
const resultsPage = ref(1)
const resultsPageSize = ref(20)
const resultsTotal = ref(0)
const events = ref([])
const subtasks = ref([])
const lineage = ref({})
const reportStatus = ref(null)
let timer

const pageState = computed(() => deriveAsyncState({
  loading: loading.value && !createdOnce.value,
  error: loadError.value,
  forbidden: false,
  items: task.value?.id ? [task.value] : [],
  createdOnce: createdOnce.value,
}))

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/tasks')
}

function loadErr(e, fallback) {
  const d = e?.response?.data
  const msg = d?.message || d?.detail || e?.message
  return typeof msg === 'string' && msg ? msg : fallback
}

const statusLabel = computed(() => {
  const t = task.value || {}
  const tags = []
  if (t.trial_run) tags.push('试跑')
  if (t.simulation) tags.push('simulation')
  if (t.cancel_requested && t.status === 'running') tags.push('取消中')
  return tags.length ? `${t.status}（${tags.join('/')}）` : (t.status || '-')
})

const budgetLabel = computed(() => {
  const t = task.value || {}
  if (t.status === 'paused_budget') return 'paused_budget'
  const q = Number(t.token_quota || 0)
  const u = Number(t.tokens_used || 0)
  if (!q) return '未设配额'
  return `${u}/${q}${u >= q ? '（耗尽）' : ''}`
})

const reportJobStatusType = computed(() => {
  const s = reportStatus.value?.job?.status
  if (s === 'ready') return 'success'
  if (s === 'failed') return 'danger'
  return 'info'
})

async function load() {
  loadError.value = ''
  try {
    task.value = await tasksApi.get(route.params.id)
    const [res, ev, st] = await Promise.all([
      tasksApi.results(route.params.id, { page: resultsPage.value, page_size: resultsPageSize.value }),
      tasksApi.events(route.params.id),
      tasksApi.subtasks(route.params.id)
    ])
    results.value = res.items || []
    resultsTotal.value = res.total || 0
    events.value = ev.items || []
    subtasks.value = st.items || []
    createdOnce.value = true
    try {
      lineage.value = await tasksApi.lineage(route.params.id)
    } catch {
      lineage.value = {}
    }
    try {
      reportStatus.value = await tasksApi.reportStatus(route.params.id)
    } catch {
      reportStatus.value = null
    }
  } catch (e) {
    loadError.value = loadErr(e, '任务详情加载失败')
  }
}

async function run() {
  await tasksApi.run(route.params.id)
  ElMessage.success('已开始执行')
  load()
}

async function cancel() {
  await tasksApi.cancel(route.params.id)
  ElMessage.success('已请求取消')
  load()
}

async function retry() {
  await tasksApi.retry(route.params.id)
  ElMessage.success('已重试入队')
  load()
}

async function download(fmt = 'json') {
  try {
    const blob = await tasksApi.report(route.params.id, { fmt })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `task-${route.params.id}.${fmt}`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || `${fmt} 导出失败`)
  }
}

async function renderReport() {
  try {
    const res = await tasksApi.renderReport(route.params.id)
    if (res.status === 'ready') ElMessage.success('报告已渲染')
    else ElMessage.warning(res.error_message || res.status)
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '渲染失败')
  }
}

onMounted(async () => {
  loading.value = true
  try { await load() } finally { loading.value = false }
  timer = setInterval(load, 2000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.block { margin-bottom: 16px; }
.pagination { margin-top: 12px; justify-content: flex-end; }
.pager-line { margin-top: 12px; font-size: 13px; color: var(--text-secondary); }
.stat-label { color: var(--text-secondary); font-size: 13px; }
.stat-value { margin-top: 8px; font-size: 22px; font-weight: 600; }
.ops { display: flex; flex-wrap: wrap; gap: 8px; }
.report-head { display: flex; justify-content: space-between; align-items: center; }
.fmt-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.fmt-chip {
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-blank);
  border-radius: 10px;
  padding: 8px 12px;
  min-width: 88px;
  text-align: left;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.fmt-chip:disabled { opacity: 0.55; cursor: not-allowed; }
.fmt-chip.ready { border-color: #67c23a55; }
.fmt-chip.failed { border-color: #f56c6c88; }
.fmt-chip.missing { border-style: dashed; }
.fmt-chip strong { text-transform: uppercase; font-size: 12px; }
.fmt-chip span { font-size: 12px; color: var(--text-secondary); }
.fmt-chip em { font-style: normal; font-size: 11px; color: #f56c6c; }
.evidence-hint { margin: 12px 0 0; font-size: 12px; color: var(--text-secondary); }
</style>
