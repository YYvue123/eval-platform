<template>
  <div class="obs">
    <header class="obs-hero">
      <div class="obs-hero__glow" aria-hidden="true" />
      <div class="obs-hero__grid" aria-hidden="true" />
      <div class="obs-hero__copy">
        <p class="obs-kicker">Cohort · Frozen Scale · Evidence</p>
        <h1 class="obs-title">模型观测榜</h1>
        <p class="obs-sub">仅正式结果入榜；同 cohort 比较；缺指标不填零；发布可回滚至上一合格快照。</p>
      </div>
      <div class="obs-actions">
        <button v-if="userStore.hasPermission('leaderboard:edit')" class="obs-btn obs-btn--ghost" type="button" @click="refresh">刷新快照</button>
        <button v-if="userStore.hasPermission('leaderboard:edit')" class="obs-btn obs-btn--copper" type="button" @click="publish">发布正式榜</button>
        <button v-if="userStore.hasPermission('leaderboard:edit')" class="obs-btn obs-btn--ghost" type="button" @click="rollback">回滚</button>
        <button class="obs-btn obs-btn--ghost" type="button" @click="exportCsv">导出 CSV</button>
      </div>
    </header>

    <div v-if="stale" class="obs-banner">数据更新异常，正在展示上次快照</div>

    <section class="obs-meta">
      <div class="obs-chip"><span>榜单</span><strong>{{ boardLabel }}</strong></div>
      <div class="obs-chip"><span>Cohort</span><strong class="mono">{{ cohortId || '—' }}</strong></div>
      <div class="obs-chip"><span>排除</span><strong>{{ excludedTotal }}</strong></div>
      <div class="obs-chip"><span>发布</span><strong>{{ releaseId ? `#${releaseId}` : '未发布' }}</strong></div>
      <div v-if="frozenScale" class="obs-chip"><span>冻结尺度</span><strong class="mono">{{ frozenScale.lo?.toFixed?.(3) }} → {{ frozenScale.hi?.toFixed?.(3) }}</strong></div>
    </section>

    <div class="obs-toolbar">
      <div class="obs-tabs" role="tablist">
        <button v-for="b in boards" :key="b.value" type="button" class="obs-tab" :class="{ active: board === b.value }" @click="switchBoard(b.value)">{{ b.label }}</button>
      </div>
      <div class="obs-filters">
        <input v-model="industry" class="obs-input" placeholder="行业" @change="loadData" />
        <input v-model="scene" class="obs-input" placeholder="场景" @change="loadData" />
      </div>
    </div>

    <section v-if="podium.length" class="obs-podium">
      <article
        v-for="(row, idx) in podium"
        :key="row.model_id + '-' + idx"
        class="podium-card"
        :class="'place-' + (idx + 1)"
        :style="{ animationDelay: `${idx * 80}ms` }"
        @click="toggleSelect(row)"
      >
        <div class="podium-rank mono">{{ formatRank(row.rank) }}</div>
        <h3>{{ row.model_name }}</h3>
        <p class="podium-score mono">{{ formatScore(row.norm_score) }}</p>
        <p class="podium-sub">{{ row.scene || '—' }} · {{ ((row.pass_rate || 0) * 100).toFixed(0) }}% pass</p>
      </article>
    </section>

    <section class="obs-table-wrap">
      <table class="obs-table">
        <thead>
          <tr>
            <th></th>
            <th>排名</th>
            <th>模型</th>
            <th>行业</th>
            <th>场景</th>
            <th>平均分</th>
            <th>归一化</th>
            <th v-if="board === 'value'">成本</th>
            <th>通过率</th>
            <th>来源任务</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, i) in items"
            :key="row.model_id + '-' + row.task_id"
            :class="{ selected: isSelected(row), missing: row.missing_metric }"
            :style="{ animationDelay: `${Math.min(i, 12) * 40}ms` }"
            @click="toggleSelect(row)"
          >
            <td><span class="sel-dot" :class="{ on: isSelected(row) }" /></td>
            <td class="mono">{{ formatRank(row.rank) }}<em v-if="row.tied">=</em></td>
            <td class="name">{{ row.model_name }}</td>
            <td>{{ row.industry || '—' }}</td>
            <td>{{ row.scene || '—' }}</td>
            <td class="mono">{{ formatScore(row.avg_score) }}</td>
            <td class="mono accent">{{ formatScore(row.norm_score) }}</td>
            <td v-if="board === 'value'" class="mono">{{ formatScore(row.cost) }}</td>
            <td class="mono">{{ row.pass_rate == null ? '—' : ((row.pass_rate || 0) * 100).toFixed(1) + '%' }}</td>
            <td class="muted">{{ row.task_name }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!items.length" class="obs-empty">当前 cohort 暂无可比正式结果</p>
    </section>

    <section class="obs-bottom">
      <div class="obs-panel">
        <div class="obs-panel__head">
          <h2>雷达对比</h2>
          <span class="muted">选 2–5 个模型 · 缺场景为 null</span>
        </div>
        <div ref="radarEl" class="radar" />
      </div>
      <div v-if="userStore.hasPermission('leaderboard:edit')" class="obs-panel">
        <div class="obs-panel__head">
          <h2>成本表</h2>
          <span class="muted">可复算账单</span>
        </div>
        <div class="cost-list">
          <div v-for="row in costs" :key="row.model_id" class="cost-row">
            <span>{{ row.model_name }}</span>
            <label>Token/千
              <input type="number" step="0.001" v-model.number="row.token_price_per_1k" @change="saveCost(row)" />
            </label>
            <label>时延/秒
              <input type="number" step="0.001" v-model.number="row.latency_price_per_sec" @change="saveCost(row)" />
            </label>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { leaderboardApi } from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const items = ref([])
const costs = ref([])
const industry = ref('')
const scene = ref('')
const board = ref('overall')
const stale = ref(false)
const cohortId = ref('')
const excludedTotal = ref(0)
const releaseId = ref(null)
const frozenScale = ref(null)
const selected = ref([])
const radarEl = ref(null)
let chart

const boards = [
  { value: 'overall', label: '综合' },
  { value: 'ability', label: '单项' },
  { value: 'special', label: '专项' },
  { value: 'value', label: '性价比' },
]

const boardLabel = computed(() => boards.find((b) => b.value === board.value)?.label || board.value)
const podium = computed(() => items.value.filter((r) => r.rank != null).slice(0, 3))

function formatRank(r) {
  return r == null ? '—' : String(r).padStart(2, '0')
}
function formatScore(v) {
  return v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(3)
}
function isSelected(row) {
  return selected.value.some((s) => s.model_id === row.model_id)
}
function toggleSelect(row) {
  if (isSelected(row)) selected.value = selected.value.filter((s) => s.model_id !== row.model_id)
  else if (selected.value.length < 5) selected.value = [...selected.value, row]
  drawRadar()
}

async function switchBoard(v) {
  board.value = v
  await loadData()
}

async function loadData() {
  const res = await leaderboardApi.list({ board: board.value, industry: industry.value, scene: scene.value })
  items.value = res.items || []
  stale.value = !!res.stale
  cohortId.value = res.cohort_id || ''
  excludedTotal.value = res.excluded_total || 0
  releaseId.value = res.release_id || null
  frozenScale.value = res.frozen_scale || null
  selected.value = []
  await drawRadar()
}

async function refresh() {
  await leaderboardApi.refresh({ board: board.value })
  ElMessage.success('已写入快照')
  loadData()
}

async function publish() {
  const rel = await leaderboardApi.publish({ board: board.value }, { note: 'ui-publish' })
  ElMessage.success(`已发布 #${rel.id}`)
  loadData()
}

async function rollback() {
  try {
    const rel = await leaderboardApi.rollback({ board: board.value })
    ElMessage.success(`已回滚至 #${rel.id}`)
    loadData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '回滚失败')
  }
}

async function exportCsv() {
  const blob = await leaderboardApi.export({ board: board.value, industry: industry.value, scene: scene.value })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `leaderboard-${board.value}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

async function saveCost(row) {
  await leaderboardApi.putCost(row.model_id, {
    token_price_per_1k: row.token_price_per_1k,
    latency_price_per_sec: row.latency_price_per_sec,
    gpu_hour_price: row.gpu_hour_price || 0,
  })
}

async function drawRadar() {
  if (!chart) return
  if (selected.value.length < 2) {
    chart.clear()
    return
  }
  const ids = selected.value.slice(0, 5).map((r) => r.model_id).join(',')
  const data = await leaderboardApi.radar({ model_ids: ids })
  const indicators = (data.scenes || []).map((s) => ({ name: s, max: 1 }))
  chart.setOption({
    backgroundColor: 'transparent',
    textStyle: { color: '#64748b', fontFamily: 'ui-sans-serif, system-ui, sans-serif' },
    legend: { data: (data.series || []).map((s) => s.model_name), textStyle: { color: '#64748b' }, top: 0 },
    radar: {
      indicator: indicators.length ? indicators : [{ name: 'n/a', max: 1 }],
      axisName: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: 'rgba(99,102,241,0.12)' } },
      splitArea: { areaStyle: { color: ['rgba(248,250,252,0.9)', 'rgba(99,102,241,0.04)'] } },
      axisLine: { lineStyle: { color: 'rgba(148,163,184,0.35)' } },
    },
    series: [{
      type: 'radar',
      data: (data.series || []).map((s) => ({
        name: s.model_name,
        value: (s.values || []).map((v) => (v == null ? 0 : v)),
        lineStyle: { width: 2 },
        areaStyle: { opacity: 0.1 },
      })),
    }],
    color: ['#6366f1', '#0ea5e9', '#22c55e', '#f59e0b', '#64748b'],
  })
}

onMounted(async () => {
  await loadData()
  if (userStore.hasPermission('leaderboard:edit')) {
    const c = await leaderboardApi.costs()
    costs.value = c.items || []
  }
  await nextTick()
  if (radarEl.value) chart = echarts.init(radarEl.value)
})
onUnmounted(() => chart?.dispose())
</script>

<style scoped>
.obs {
  --surface: var(--bg-card, #fff);
  --surface-2: var(--bg-page, #f8fafc);
  --line: var(--border-color, #e2e8f0);
  --accent: var(--color-primary, #6366f1);
  --accent-soft: rgba(99, 102, 241, 0.1);
  --ink: var(--text-primary, #1e293b);
  --muted: var(--text-secondary, #64748b);
  --good: var(--color-success, #22c55e);
  font-family: ui-sans-serif, system-ui, 'Segoe UI', sans-serif;
  color: var(--ink);
  margin: -8px -4px 0;
  padding: 8px 4px 28px;
}

.obs-hero {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-xl, 18px);
  background:
    linear-gradient(135deg, rgba(99,102,241,0.08), transparent 42%),
    linear-gradient(180deg, #ffffff, #f8fafc);
  border: 1px solid var(--line);
  box-shadow: var(--shadow-sm);
  padding: 28px 28px 24px;
  display: flex;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  isolation: isolate;
}
.obs-hero__glow {
  position: absolute;
  inset: -30% auto auto 55%;
  width: 360px;
  height: 240px;
  background: radial-gradient(circle, rgba(99,102,241,0.18), transparent 70%);
  filter: blur(8px);
  z-index: 0;
  animation: drift 8s ease-in-out infinite alternate;
}
.obs-hero__grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(148,163,184,0.12) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148,163,184,0.12) 1px, transparent 1px);
  background-size: 28px 28px;
  mask-image: linear-gradient(180deg, rgba(0,0,0,0.35), transparent 80%);
  z-index: 0;
  pointer-events: none;
}
.obs-hero__copy, .obs-actions { position: relative; z-index: 1; }
.obs-kicker {
  margin: 0 0 8px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  font-size: 11px;
  color: var(--accent);
  font-family: ui-monospace, 'Cascadia Code', 'Consolas', monospace;
}
.obs-title {
  margin: 0;
  font-family: ui-sans-serif, system-ui, 'Segoe UI', sans-serif;
  font-weight: 800;
  font-size: clamp(28px, 4vw, 40px);
  letter-spacing: -0.03em;
  color: var(--ink);
  animation: rise 0.6s ease both;
}
.obs-sub {
  margin: 10px 0 0;
  max-width: 520px;
  color: var(--muted);
  line-height: 1.55;
  animation: rise 0.7s ease both;
}
.obs-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-start; }
.obs-btn {
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink);
  padding: 8px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: transform 0.15s ease, background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}
.obs-btn:hover {
  transform: translateY(-1px);
  border-color: var(--accent);
  box-shadow: var(--shadow-sm);
}
.obs-btn--copper {
  background: var(--accent);
  color: #fff;
  border-color: transparent;
  font-weight: 600;
}
.obs-btn--copper:hover { background: var(--color-primary-dark, #4f46e5); }
.obs-btn--ghost { background: var(--surface-2); }

.obs-banner {
  margin-top: 12px;
  padding: 10px 14px;
  border-radius: 10px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  color: #b45309;
}

.obs-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 16px 0 12px;
}
.obs-chip {
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding: 8px 12px;
  border-radius: 10px;
  background: var(--surface);
  border: 1px solid var(--line);
  box-shadow: var(--shadow-sm);
  font-size: 12px;
}
.obs-chip span { color: var(--muted); }
.obs-chip strong { color: var(--ink); font-weight: 600; }
.mono { font-family: ui-monospace, 'Cascadia Code', 'Consolas', monospace; }

.obs-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.obs-tabs {
  display: inline-flex;
  padding: 4px;
  border-radius: 12px;
  background: var(--surface);
  border: 1px solid var(--line);
}
.obs-tab {
  border: 0;
  background: transparent;
  color: var(--muted);
  padding: 8px 14px;
  border-radius: 9px;
  cursor: pointer;
  font-family: inherit;
}
.obs-tab.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}
.obs-filters { display: flex; gap: 8px; }
.obs-input {
  width: 120px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink);
  padding: 8px 10px;
  outline: none;
}
.obs-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }

.obs-podium {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.podium-card {
  position: relative;
  border-radius: 16px;
  padding: 18px 16px 16px;
  background: var(--surface);
  border: 1px solid var(--line);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  overflow: hidden;
  animation: rise 0.55s ease both;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}
.podium-card:hover {
  transform: translateY(-3px);
  border-color: rgba(99,102,241,0.35);
  box-shadow: var(--shadow-md);
}
.podium-card.place-1 {
  background: linear-gradient(165deg, #eef2ff, #ffffff);
  border-color: rgba(99,102,241,0.35);
}
.podium-card.place-2 { transform: translateY(8px); }
.podium-card.place-3 { transform: translateY(14px); }
.podium-rank {
  font-size: 28px;
  color: var(--accent);
  font-weight: 600;
  line-height: 1;
}
.podium-card h3 {
  margin: 10px 0 6px;
  font-family: ui-sans-serif, system-ui, 'Segoe UI', sans-serif;
  font-size: 18px;
  color: var(--ink);
}
.podium-score { font-size: 22px; color: var(--accent); margin: 0; }
.podium-sub { margin: 6px 0 0; color: var(--muted); font-size: 12px; }

.obs-table-wrap {
  border-radius: 16px;
  border: 1px solid var(--line);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  overflow: auto;
}
.obs-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.obs-table th {
  text-align: left;
  padding: 12px 14px;
  color: var(--muted);
  font-weight: 500;
  border-bottom: 1px solid var(--line);
  background: var(--surface-2);
  white-space: nowrap;
}
.obs-table td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-light, #f1f5f9);
  animation: rise 0.45s ease both;
}
.obs-table tr { cursor: pointer; transition: background 0.15s ease; }
.obs-table tr:hover, .obs-table tr.selected { background: var(--accent-soft); }
.obs-table tr.missing { opacity: 0.55; }
.obs-table .name { color: var(--ink); font-weight: 500; }
.obs-table .accent { color: var(--accent); }
.obs-table .muted, .muted { color: var(--muted); }
.obs-table em { font-style: normal; color: var(--good); margin-left: 4px; }
.sel-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
  border: 1px solid var(--line);
  background: #fff;
}
.sel-dot.on {
  background: var(--accent);
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.obs-empty { padding: 28px; text-align: center; color: var(--muted); }

.obs-bottom {
  margin-top: 16px;
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 12px;
}
.obs-panel {
  border-radius: 16px;
  border: 1px solid var(--line);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 16px;
}
.obs-panel__head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 10px;
}
.obs-panel__head h2 {
  margin: 0;
  font-family: ui-sans-serif, system-ui, 'Segoe UI', sans-serif;
  font-size: 16px;
  color: var(--ink);
}
.radar { height: 300px; }
.cost-list { display: flex; flex-direction: column; gap: 10px; max-height: 300px; overflow: auto; }
.cost-row {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr;
  gap: 8px;
  align-items: center;
  font-size: 12px;
}
.cost-row label { display: flex; flex-direction: column; gap: 4px; color: var(--muted); }
.cost-row input {
  border-radius: 8px;
  border: 1px solid var(--line);
  background: var(--surface-2);
  color: var(--ink);
  padding: 6px 8px;
}

@keyframes rise {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes drift {
  from { transform: translateX(-12px); }
  to { transform: translateX(18px); }
}

@media (max-width: 960px) {
  .obs-podium, .obs-bottom { grid-template-columns: 1fr; }
  .podium-card.place-2, .podium-card.place-3 { transform: none; }
  .cost-row { grid-template-columns: 1fr; }
}

html.dark .obs {
  --surface: var(--bg-card);
  --surface-2: var(--bg-page);
  --line: var(--border-color);
  --ink: var(--text-primary);
  --muted: var(--text-secondary);
}
html.dark .obs-hero {
  background:
    linear-gradient(135deg, rgba(99,102,241,0.16), transparent 42%),
    linear-gradient(180deg, #1e293b, #0f172a);
}
html.dark .obs-banner {
  background: rgba(245, 158, 11, 0.12);
  border-color: rgba(245, 158, 11, 0.35);
  color: #fbbf24;
}
html.dark .podium-card.place-1 {
  background: linear-gradient(165deg, rgba(99,102,241,0.18), #1e293b);
}
</style>
