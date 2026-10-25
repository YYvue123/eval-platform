<template>
  <div class="dashboard-page">
    <header class="desk-head">
      <div>
        <span class="kicker">EVALUATION DESK</span>
        <h2 class="page-title">工作台 <span class="desk-date">{{ todayText }}</span></h2>
        <p class="page-desc">{{ userStore.displayName || '你好' }}，从这里掌握评测进展，继续推进重要的事。</p>
      </div>
      <div class="head-actions">
        <span class="sync-time">{{ lastUpdated ? `更新于 ${lastUpdated}` : '正在获取数据' }}</span>
        <el-button v-if="userStore.hasPermission('dashboard:view')" :loading="loading" @click="loadDashboard">刷新数据</el-button>
        <el-button v-if="userStore.hasPermission('task:create') && userStore.hasPermission('task:list')" type="primary" @click="go('/tasks')">进入任务管理 →</el-button>
      </div>
    </header>

    <el-alert
      v-if="route.query.denied"
      type="warning"
      :closable="true"
      :title="`无权访问：${route.query.denied}`"
      style="margin-bottom: 0"
    />

    <el-skeleton v-if="loading && !lastUpdated" :rows="8" animated />
    <PageAsyncState v-else-if="loadError" state="error" :errorMessage="loadError" />
    <template v-else>
      <section class="focus-strip" aria-label="工作提示">
        <div><span class="focus-dot" /><strong>{{ attentionCount ? `${attentionCount} 项等待推进` : '评测工作有序推进' }}</strong><p>待审 {{ workbench.pending_reviews || 0 }} 项 · 编排待确认 {{ workbench.pending_approvals || 0 }} 项 · 异常 {{ exceptionCount }} 项</p></div>
        <span class="scope-note">当前全平台任务概览 · 执行成功不代表评测通过</span>
      </section>
      <section class="metric-grid" aria-label="运行概览">
        <button
          v-for="(item, index) in metrics"
          :key="item.key"
          type="button"
          class="metric"
          :style="{ '--accent': item.accent, animationDelay: `${index * 40}ms` }"
          :disabled="!userStore.hasPermission(item.permission)"
          @click="go(item.path, item.query)"
        >
          <span class="metric-label">{{ item.label }}</span>
          <span class="metric-value">{{ item.value }}</span>
          <span class="metric-hint">{{ item.hint }}</span>
        </button>
      </section>

      <section class="insight-grid">
        <article class="panel trend-panel">
          <header class="panel-head">
            <div><span class="kicker">EVALUATION ACTIVITY</span><h3>评测任务趋势</h3><p>按创建日期统计；异常为该日创建任务中当前失败或部分失败的数量。北京时间。</p></div>
            <div class="period-switch" aria-label="趋势统计周期"><button v-for="days in [7, 14, 30]" :key="days" type="button" :aria-pressed="period === days" :class="{ active: period === days }" @click="period = days">{{ days }} 天</button></div>
          </header>
          <div class="trend-summary"><strong>{{ periodTotal }}</strong><span>个新建任务</span><i /><strong class="exception-number">{{ periodFailed }}</strong><span>个当前异常</span></div>
          <LeaderboardChart v-if="periodTotal" :option="activityOption" height="250px" :label="`近${period}天新建任务${periodTotal}个，当前异常${periodFailed}个`" />
          <div v-else class="insight-empty"><span>还没有新的评测活动</span><p>近 {{ period }} 天没有创建任务，可切换更长周期或从任务管理开始。</p></div>
        </article>
        <article class="panel">
          <header class="panel-head"><div><span class="kicker">EVALUATION COVERAGE</span><h3>评测任务分布</h3><p>按任务类型统计全部任务，了解评测投入方向。</p></div></header>
          <LeaderboardChart v-if="typeRows.length" :option="typeOption" height="290px" label="各评测任务类型数量" />
          <div v-else class="insight-empty"><span>等待第一项评测</span><p>创建任务后展示各类型的任务数量。</p></div>
        </article>
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
              <button v-for="item in statusSlices" :key="item.status" type="button" class="legend-btn" :disabled="!userStore.hasPermission('task:list')" @click="go('/tasks', { status: item.status })">
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
              <h3>执行队列</h3>
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
                <el-button v-if="userStore.hasPermission('task:view')" link type="primary" @click="$router.push(`/tasks/${row.id}`)">查看</el-button>
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
              <h3>优先处理</h3>
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
                <el-button v-if="userStore.hasPermission(row.kind === 'agent_confirm' ? 'agent:list' : 'task:view')" link type="primary" @click="$router.push(row.href)">处理</el-button>
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
                v-permission="s.permission"
                @click="go(s.path)"
              ><span class="shortcut-name">{{ s.label }} <span aria-hidden="true">↗</span></span><span class="shortcut-desc">{{ shortcutDescriptions[s.path] }}</span></el-button>
            </div>
            <p v-if="!shortcuts.length" class="hint">当前角色无可写入口，请联系管理员授权。</p>
          </article>
          <article class="panel">
            <header class="panel-head">
              <div>
                <span class="kicker">EXCEPTIONS</span>
                <h3>需要关注的异常</h3>
              </div>
              <span class="count">{{ workbench.failed?.length || 0 }}</span>
            </header>
            <el-table v-if="workbench.failed?.length" :data="workbench.failed" size="small">
              <el-table-column prop="name" label="任务" min-width="140" show-overflow-tooltip />
              <el-table-column prop="error_message" label="原因" show-overflow-tooltip />
              <el-table-column width="80">
                <template #default="{ row }">
                  <el-button v-if="userStore.hasPermission('task:view')" link type="primary" @click="$router.push(`/tasks/${row.id}`)">查看</el-button>
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
            <h3>最近评测动态</h3>
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
          <el-table-column label="" width="90">
            <template #default="{ row }">
              <el-button v-if="userStore.hasPermission('task:view')" link type="primary" @click="$router.push(`/tasks/${row.id}`)">查看</el-button>
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
const loading = ref(false)
const lastUpdated = ref('')
const period = ref(14)
const todayText = new Date().toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai', month: 'long', day: 'numeric', weekday: 'long' })
const exceptionCount = computed(() => (workbench.value.status_counts?.failed || 0) + (workbench.value.status_counts?.partial_failed || 0))
const attentionCount = computed(() => (workbench.value.pending_reviews || 0) + (workbench.value.pending_approvals || 0) + exceptionCount.value)
const periodRows = computed(() => (workbench.value.activity || []).slice(-period.value))
const periodTotal = computed(() => periodRows.value.reduce((sum, row) => sum + row.created, 0))
const periodFailed = computed(() => periodRows.value.reduce((sum, row) => sum + row.failed, 0))
const typeRows = computed(() => [...(workbench.value.task_types || [])].sort((a, b) => b.count - a.count))
const typeLabel = (value) => ({ capability: '能力评测', scene: '场景应用', industry: '行业专项', safety: '安全评测', performance: '性能评测', robustness: '鲁棒性评测', unknown: '未分类' }[value] || value)
const activityOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { bottom: 0, data: ['新建任务', '当前异常'], textStyle: { color: '#7a8aa4' } },
  grid: { left: 36, right: 16, top: 20, bottom: 58, containLabel: true },
  xAxis: { type: 'category', data: periodRows.value.map(row => row.date.slice(5)), axisTick: { show: false }, axisLine: { lineStyle: { color: '#dce5f1' } }, axisLabel: { color: '#7a8aa4' } },
  yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#edf1f7', type: 'dashed' } }, axisLabel: { color: '#7a8aa4' } },
  series: [
    { name: '新建任务', type: 'bar', barMaxWidth: 22, data: periodRows.value.map(row => row.created), itemStyle: { color: '#2773cc', borderRadius: [4, 4, 0, 0] } },
    { name: '当前异常', type: 'line', data: periodRows.value.map(row => row.failed), symbolSize: 6, itemStyle: { color: '#d97706' }, lineStyle: { width: 2 } },
  ],
}))
const typeOption = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 12, right: 40, top: 22, bottom: 20, containLabel: true },
  xAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#edf1f7', type: 'dashed' } }, axisLabel: { color: '#7a8aa4' } },
  yAxis: { type: 'category', inverse: true, data: typeRows.value.map(row => typeLabel(row.type)), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#526179' } },
  series: [{ name: '任务数', type: 'bar', barMaxWidth: 22, label: { show: true, position: 'right', color: '#526179' }, data: typeRows.value.map((row, index) => ({ value: row.count, itemStyle: { color: ['#2773cc', '#15956a', '#68b7db', '#d97706'][index % 4], borderRadius: [0, 4, 4, 0] } })) }],
}))

const metrics = computed(() => {
  const list = [
    { key: 'running', label: '进行中任务', value: stats.value.running_task_count ?? workbench.value.running?.length ?? 0, hint: '排队与执行中 · 查看执行列表', path: '/tasks', query: { status: 'running' }, accent: '#2563eb' },
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
  return list.map((item) => ({ ...item, permission: ({ '/tasks': 'task:list', '/agents': 'agent:list', '/datasets': 'dataset:list', '/models': 'model:list', '/resources': 'resource:list', '/services': 'service:list', '/leaderboard': 'leaderboard:view' })[item.path] }))
})

const shortcutDescriptions = { '/agents': '从评测目标开始编排', '/tasks': '配置并跟踪评测执行', '/datasets': '准备可复用的评测样本', '/models': '接入被测模型与版本', '/resources': '管理评测工具与裁判', '/services': '跟进评测交付流程', '/leaderboard': '查看模型表现与对比' }

const shortcuts = computed(() => {
  const list = []
  if (userStore.hasPermission('agent:invoke')) list.push({ path: '/agents', label: '发起编排评测' })
  if (userStore.hasPermission('task:create')) list.push({ path: '/tasks', label: '创建任务' })
  if (userStore.hasPermission('dataset:create')) list.push({ path: '/datasets', label: '导入数据' })
  if (userStore.hasPermission('model:create')) list.push({ path: '/models', label: '注册模型' })
  if (userStore.hasPermission('resource:list')) list.push({ path: '/resources', label: '工具中心' })
  if (userStore.hasPermission('service:create')) list.push({ path: '/services', label: '评测服务' })
  if (userStore.hasPermission('leaderboard:view')) list.push({ path: '/leaderboard', label: '模型榜单' })
  return list.map((item) => ({ ...item, permission: ({ '/tasks': 'task:list', '/agents': 'agent:list', '/datasets': 'dataset:list', '/models': 'model:list', '/resources': 'resource:list', '/services': 'service:list', '/leaderboard': 'leaderboard:view' })[item.path] }))
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

async function loadDashboard() {
  if (loading.value) return
  loading.value = true
  loadError.value = ''
  try {
    const [nextStats, nextWorkbench] = await Promise.all([
      dashboardApi.getStats(),
      dashboardApi.getWorkbench(),
    ])
    stats.value = nextStats
    workbench.value = nextWorkbench
    lastUpdated.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    loadError.value = ''
  } catch (err) {
    loadError.value = messageOf(err, '工作台加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(loadDashboard)
</script>

<style scoped>
.desk-date { margin-left: 14px; font-size: 13px; font-weight: 400; color: var(--text-secondary); letter-spacing: 0; }
.head-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.sync-time, .scope-note { font-size: 11px; color: var(--text-secondary); }
.focus-strip { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 20px 24px; border: 1px solid var(--border-color); border-left: 4px solid #2773cc; border-radius: 12px; background: linear-gradient(110deg, color-mix(in srgb, var(--color-primary) 9%, var(--bg-card)), var(--bg-card)); }
.focus-strip strong { font-size: 16px; color: var(--text-primary); }
.focus-strip p { margin: 8px 0 0 18px; font-size: 12px; color: var(--text-secondary); }
.focus-dot { display: inline-block; width: 7px; height: 7px; margin-right: 10px; background: #2773cc; border-radius: 50%; }
.insight-grid { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: 16px; }
.period-switch { display: flex; flex-shrink: 0; background: var(--bg-page); border: 1px solid var(--border-color); padding: 3px; border-radius: 8px; }
.period-switch button { border: 0; background: transparent; color: var(--text-secondary); padding: 6px 10px; border-radius: 5px; cursor: pointer; font: inherit; font-size: 12px; }
.period-switch .active { background: var(--bg-card); color: var(--color-primary); box-shadow: var(--shadow-sm); }
.trend-summary { display: flex; align-items: baseline; gap: 8px; color: var(--text-secondary); font-size: 12px; }
.trend-summary strong { font: 600 28px 'Bahnschrift', 'DIN Alternate', sans-serif; color: var(--text-primary); }
.trend-summary .exception-number { color: #d97706; }
.trend-summary i { height: 20px; width: 1px; margin: 0 12px; background: var(--border-color); }
.insight-empty { min-height: 230px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; color: var(--text-secondary); font-size: 14px; }
.insight-empty p { font-size: 12px; line-height: 1.8; max-width: 290px; }
button:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 3px; }
button:disabled { cursor: default; }
@media (max-width: 1000px) { .insight-grid { grid-template-columns: 1fr; } .focus-strip { align-items: flex-start; flex-direction: column; gap: 12px; } }
@media (max-width: 680px) { .desk-date { display: block; margin: 8px 0 0; } .sync-time { width: 100%; } }

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
.shortcuts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.shortcuts .el-button { display: flex; height: auto; min-height: 68px; margin: 0; padding: 14px; justify-content: flex-start; white-space: normal; }
.shortcuts :deep(.el-button > span) { display: flex; flex-direction: column; align-items: stretch; width: 100%; gap: 8px; }
.shortcut-name { display: flex; justify-content: space-between; gap: 8px; font-weight: 600; color: var(--text-primary); }
.shortcut-name > span { color: var(--color-primary); }
.shortcut-desc { font-size: 11px; line-height: 1.5; color: var(--text-secondary); }
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
