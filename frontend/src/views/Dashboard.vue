<template>
  <div class="dashboard-page">
    <header class="desk-head">
      <div>
        <span class="kicker">EVALUATION DESK</span>
        <h2 class="page-title">工作台</h2>
        <p class="page-desc">待办、任务构成、进行中的队列和最近结果。数字可下钻。</p>
      </div>
    </header>

    <el-alert
      v-if="route.query.denied"
      type="warning"
      :closable="true"
      :title="`无权访问：${route.query.denied}`"
      style="margin-bottom: 0"
    />

    <PageAsyncState v-if="loadError" state="error" :errorMessage="loadError" />
    <template v-else>
      <section class="metric-grid" aria-label="运行概览">
        <button
          v-for="(item, index) in metrics"
          :key="item.key"
          type="button"
          class="metric"
          :style="{ '--accent': item.accent, animationDelay: `${index * 40}ms` }"
          @click="go(item.path, item.query)"
        >
          <span class="metric-label">{{ item.label }}</span>
          <span class="metric-value">{{ item.value }}</span>
          <span class="metric-hint">{{ item.hint }}</span>
        </button>
      </section>

      <section class="chart-grid">
        <article class="panel">
          <header class="panel-head">
            <div>
              <span class="kicker">TASK MIX</span>
              <h3>任务状态</h3>
              <p>按当前全部任务汇总。点击图例进入对应列表。</p>
            </div>
          </header>
          <div v-if="statusSlices.length" class="chart-split">
            <LeaderboardChart :option="statusOption" height="232px" label="任务状态构成" />
            <div class="legend">
              <button v-for="item in statusSlices" :key="item.status" type="button" class="legend-btn" @click="go('/tasks', { status: item.status })">
                <i :style="{ background: item.color }" />
                <span>{{ item.label }}</span>
                <b>{{ item.value }}</b>
              </button>
            </div>
          </div>
          <p v-else class="chart-empty">还没有评测任务。创建后，这里会按状态汇总。</p>
        </article>

        <article class="panel">
          <header class="panel-head">
            <div>
              <span class="kicker">IN PROGRESS</span>
              <h3>进行中</h3>
              <p>排队和正在执行的任务。进度来自任务本身。</p>
            </div>
            <span class="count">{{ workbench.running?.length || 0 }}</span>
          </header>
          <el-table v-if="workbench.running?.length" :data="workbench.running" size="small">
            <el-table-column prop="name" label="任务" min-width="160" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <StatusBadge :phase="taskPhase(row.status)" :text="statusText(row.status)" />
              </template>
            </el-table-column>
            <el-table-column label="进度" min-width="140">
              <template #default="{ row }">
                <el-progress :percentage="Number(row.progress) || 0" :stroke-width="8" />
              </template>
            </el-table-column>
            <el-table-column width="70">
              <template #default="{ row }">
                <el-button link type="primary" @click="$router.push(`/tasks/${row.id}`)">查看</el-button>
              </template>
            </el-table-column>
          </el-table>
          <p v-else class="chart-empty">当前没有排队或执行中的任务。</p>
        </article>
      </section>

      <section class="work-grid">
        <article class="panel">
          <header class="panel-head">
            <div>
              <span class="kicker">INBOX</span>
              <h3>待办</h3>
            </div>
            <span class="count">{{ workbench.todos?.length || 0 }}</span>
          </header>
          <el-table v-if="workbench.todos?.length" :data="workbench.todos" size="small">
            <el-table-column prop="kind" label="类型" width="120">
              <template #default="{ row }">{{ kindLabel(row.kind) }}</template>
            </el-table-column>
            <el-table-column prop="title" label="事项" min-width="140" show-overflow-tooltip />
            <el-table-column width="80">
              <template #default="{ row }">
                <el-button link type="primary" @click="$router.push(row.href)">处理</el-button>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState
            v-else
            type="default"
            title="暂无待办"
            description="可以从快捷入口创建评测或导入数据起步。"
            :show-action="false"
          />
        </article>

        <div class="stack">
          <article class="panel">
            <header class="panel-head">
              <div>
                <span class="kicker">GO TO</span>
                <h3>快捷入口</h3>
              </div>
            </header>
            <div class="shortcuts">
              <el-button
                v-for="s in shortcuts"
                :key="s.path"
                @click="go(s.path)"
              >{{ s.label }}</el-button>
            </div>
            <p v-if="!shortcuts.length" class="hint">当前角色无可写入口，请联系管理员授权。</p>
          </article>
          <article class="panel">
            <header class="panel-head">
              <div>
                <span class="kicker">EXCEPTIONS</span>
                <h3>异常任务</h3>
              </div>
              <span class="count">{{ workbench.failed?.length || 0 }}</span>
            </header>
            <el-table v-if="workbench.failed?.length" :data="workbench.failed" size="small">
              <el-table-column prop="name" label="任务" min-width="140" show-overflow-tooltip />
              <el-table-column prop="error_message" label="原因" show-overflow-tooltip />
              <el-table-column width="80">
                <template #default="{ row }">
                  <el-button link type="primary" @click="$router.push(`/tasks/${row.id}`)">查看</el-button>
                </template>
              </el-table-column>
            </el-table>
            <EmptyState
              v-else
              type="default"
              title="暂无异常任务"
              description="失败任务会显示在这里，可从列表进入详情处理。"
              :show-action="false"
            />
          </article>
        </div>
      </section>

      <article class="panel">
        <header class="panel-head">
          <div>
            <span class="kicker">LATEST</span>
            <h3>最近任务</h3>
          </div>
        </header>
        <el-table v-if="workbench.recent?.length" :data="workbench.recent" size="small">
          <el-table-column prop="name" label="任务" min-width="180" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <StatusBadge :phase="taskPhase(row.status)" :text="statusText(row.status)" />
            </template>
          </el-table-column>
          <el-table-column label="更新" width="120">
            <template #default="{ row }">{{ timeText(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="通过率" width="110">
            <template #default="{ row }">
              {{ row.pass_rate == null ? '—' : `${((row.pass_rate || 0) * 100).toFixed(1)}%` }}
            </template>
          </el-table-column>
          <el-table-column label="" width="90">
            <template #default="{ row }">
              <el-button link type="primary" @click="$router.push(`/tasks/${row.id}`)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
        <EmptyState
          v-else
          type="task"
          action-text="去创建任务"
          :show-action="userStore.hasPermission('task:create')"
          @action="go('/tasks')"
        />
      </article>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { dashboardApi } from '@/api'
import { useUserStore } from '@/stores/user'
import EmptyState from '@/components/EmptyState.vue'
import LeaderboardChart from '@/components/LeaderboardChart.vue'
import PageAsyncState from '@/components/PageAsyncState.vue'
import StatusBadge from '@/components/StatusBadge.vue'

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
  unknown: '未标注',
}
const STATUS_COLOR = {
  draft: '#94a3b8',
  pending_review: '#d97706',
  queued: '#6366f1',
  running: '#2563eb',
  success: '#15956a',
  failed: '#dc2626',
  partial_failed: '#ea580c',
  cancelled: '#64748b',
  paused_budget: '#b45309',
  unknown: '#94a3b8',
}
const STATUS_ORDER = ['running', 'queued', 'pending_review', 'success', 'failed', 'partial_failed', 'paused_budget', 'draft', 'cancelled', 'unknown']

const userStore = useUserStore()
const router = useRouter()
const route = useRoute()
const stats = ref({})
const workbench = ref({ todos: [], running: [], failed: [], recent: [], status_counts: {} })
const loadError = ref('')

const metrics = computed(() => {
  const list = [
    { key: 'running', label: '进行中任务', value: stats.value.running_task_count ?? workbench.value.running?.length ?? 0, hint: '打开排队列表', path: '/tasks', query: { status: 'queued' }, accent: '#2563eb' },
    { key: 'approvals', label: '待确认编排', value: workbench.value.pending_approvals ?? 0, hint: '等待确认的会话', path: '/agents', accent: '#d97706' },
    { key: 'reviews', label: '待审任务', value: workbench.value.pending_reviews ?? 0, hint: '提交后尚未放行', path: '/tasks', query: { status: 'pending_review' }, accent: '#b45309' },
    { key: 'tasks', label: '评测任务', value: stats.value.task_count ?? 0, hint: '全部任务', path: '/tasks', accent: '#6366f1' },
  ]
  if (userStore.hasPermission('dataset:list')) {
    list.push({ key: 'datasets', label: '评测数据', value: stats.value.dataset_count ?? 0, hint: '已登记数据集', path: '/datasets', accent: '#0f766e' })
  }
  if (userStore.hasPermission('model:list')) {
    list.push({ key: 'models', label: '被测模型', value: stats.value.model_count ?? 0, hint: '已注册模型', path: '/models', accent: '#0369a1' })
  }
  return list
})

const shortcuts = computed(() => {
  const list = []
  if (userStore.hasPermission('agent:invoke')) list.push({ path: '/agents', label: '发起编排评测' })
  if (userStore.hasPermission('task:create')) list.push({ path: '/tasks', label: '创建任务' })
  if (userStore.hasPermission('dataset:create')) list.push({ path: '/datasets', label: '导入数据' })
  if (userStore.hasPermission('model:create')) list.push({ path: '/models', label: '注册模型' })
  if (userStore.hasPermission('resource:list')) list.push({ path: '/resources', label: '工具中心' })
  if (userStore.hasPermission('service:create')) list.push({ path: '/services', label: '评测服务' })
  if (userStore.hasPermission('leaderboard:view')) list.push({ path: '/leaderboard', label: '模型榜单' })
  return list
})

const statusSlices = computed(() => {
  const counts = workbench.value.status_counts || {}
  const known = new Set(STATUS_ORDER)
  const extra = Object.keys(counts).filter((key) => !known.has(key))
  return [...STATUS_ORDER, ...extra]
    .filter((status) => Number(counts[status]) > 0)
    .map((status) => ({
      status,
      label: STATUS_CN[status] || status,
      value: Number(counts[status]),
      color: STATUS_COLOR[status] || '#64748b',
    }))
})

const statusOption = computed(() => {
  if (!statusSlices.value.length) return null
  const total = statusSlices.value.reduce((sum, item) => sum + item.value, 0)
  return {
    animationDuration: 420,
    tooltip: {
      trigger: 'item',
      backgroundColor: '#fff',
      borderColor: '#dce5f1',
      textStyle: { color: '#334155', fontSize: 12 },
      formatter: (item) => `${item.name}    ${item.value}（${item.percent}%）`,
    },
    title: {
      text: String(total),
      subtext: '全部任务',
      left: 'center',
      top: '38%',
      textStyle: { color: '#334155', fontSize: 28, fontWeight: 650 },
      subtextStyle: { color: '#7a8aa4', fontSize: 12 },
    },
    series: [{
      type: 'pie',
      radius: ['62%', '82%'],
      center: ['50%', '50%'],
      avoidLabelOverlap: true,
      label: { show: false },
      data: statusSlices.value.map((item) => ({
        name: item.label,
        value: item.value,
        itemStyle: { color: item.color, borderColor: '#fff', borderWidth: 3, borderRadius: 4 },
      })),
    }],
  }
})

function kindLabel(kind) {
  return ({ task_review: '任务审核', agent_confirm: '编排确认', task_failed: '任务失败' }[kind] || kind)
}

function statusText(status) {
  return STATUS_CN[status] || status
}

function taskPhase(status) {
  if (['queued', 'running'].includes(status)) return 'running'
  if (status === 'failed' || status === 'partial_failed') return 'failed'
  if (status === 'success') return 'completed'
  if (status === 'pending_review') return 'awaiting_approval'
  if (status === 'paused_budget') return 'budget_paused'
  return 'idle'
}

function timeText(value) {
  if (!value) return '—'
  const raw = String(value)
  const date = new Date(raw.endsWith('Z') || raw.includes('+') ? raw : `${raw}Z`)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function go(path, query) {
  router.push(query ? { path, query } : { path })
}

function messageOf(err, fallback) {
  const data = err?.response?.data
  const msg = data?.message ?? data?.detail ?? err?.message
  return typeof msg === 'string' && msg ? msg : fallback
}

onMounted(async () => {
  try {
    const [nextStats, nextWorkbench] = await Promise.all([
      dashboardApi.getStats(),
      dashboardApi.getWorkbench(),
    ])
    stats.value = nextStats
    workbench.value = nextWorkbench
    loadError.value = ''
  } catch (err) {
    loadError.value = messageOf(err, '工作台加载失败')
  }
})
</script>

<style scoped>
.dashboard-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1440px;
}
.kicker {
  display: block;
  font-size: 10px;
  letter-spacing: 0.18em;
  font-weight: 700;
  color: var(--color-primary);
}
.desk-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}
.desk-head .page-title { margin-top: 6px; }
.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(168px, 1fr));
  gap: 12px;
}
.metric {
  position: relative;
  overflow: hidden;
  text-align: left;
  font: inherit;
  color: inherit;
  cursor: pointer;
  padding: 14px 14px 12px 16px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  box-shadow: var(--shadow-sm);
  animation: rise 0.45s ease both;
}
.metric::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--accent);
}
.metric:hover { border-color: color-mix(in srgb, var(--accent) 45%, var(--border-color)); box-shadow: var(--shadow-md); }
.metric:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.metric-label { display: block; color: var(--text-secondary); font-size: 12px; }
.metric-value {
  display: block;
  margin-top: 8px;
  font-size: 28px;
  line-height: 1;
  font-weight: 650;
  letter-spacing: -0.04em;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}
.metric-hint { display: block; margin-top: 8px; font-size: 11px; color: var(--text-placeholder); }
.chart-grid, .work-grid {
  display: grid;
  gap: 16px;
}
.chart-grid { grid-template-columns: minmax(0, 0.92fr) minmax(0, 1.08fr); }
.work-grid { grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); }
.panel {
  min-width: 0;
  padding: 16px 18px 18px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  box-shadow: var(--shadow-sm);
}
.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.panel-head h3 {
  margin: 4px 0 0;
  font-size: 16px;
  font-weight: 650;
  letter-spacing: -0.03em;
  color: var(--text-primary);
}
.panel-head p { margin: 4px 0 0; max-width: 46em; color: var(--text-secondary); font-size: 12px; line-height: 1.55; }
.count {
  min-width: 28px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--bg-page);
  color: var(--text-secondary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  text-align: center;
}
.chart-split {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 148px;
  gap: 8px;
  align-items: center;
}
.legend { display: flex; flex-direction: column; gap: 4px; }
.legend-btn {
  display: grid;
  grid-template-columns: 8px 1fr auto;
  gap: 8px;
  align-items: center;
  width: 100%;
  padding: 5px 6px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}
.legend-btn:hover { background: var(--bg-page); color: var(--text-primary); }
.legend-btn i { width: 8px; height: 8px; border-radius: 99px; }
.legend-btn b { font-variant-numeric: tabular-nums; color: var(--text-primary); }
.chart-empty { margin: 28px 0; color: var(--text-secondary); font-size: 13px; line-height: 1.6; }
.stack { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.shortcuts { display: flex; flex-wrap: wrap; gap: 8px; }
.hint { margin: 0; color: var(--text-secondary); }
@keyframes rise {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}
@media (max-width: 1180px) {
  .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .chart-grid, .work-grid, .chart-split { grid-template-columns: 1fr; }
  .legend { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 680px) {
  .metric-grid, .legend { grid-template-columns: 1fr; }
  .desk-head { align-items: stretch; flex-direction: column; }
  .metric-value { font-size: 24px; }
  .panel-head { flex-direction: column; }
}
@media (prefers-reduced-motion: reduce) {
  .metric { animation: none; }
}
</style>
