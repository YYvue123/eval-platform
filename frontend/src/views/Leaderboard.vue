<template>
  <div class="leaderboard-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">模型榜单</h2>
        <p class="page-desc">只收录正式评测成功的结果。同一比较组内的分数才能互相排名；缺指标留空，不补 0。</p>
      </div>
      <div class="ops">
        <el-button @click="exportCsv">导出 CSV</el-button>
      </div>
    </div>

    <el-alert v-if="stale" type="warning" show-icon :closable="false" title="数据更新异常，正在展示上次快照" class="block" />

    <el-card shadow="never" class="block">
      <div class="toolbar">
        <el-radio-group v-model="board" @change="switchBoard">
          <el-radio-button v-for="b in boards" :key="b.value" :value="b.value">{{ b.label }}</el-radio-button>
        </el-radio-group>
        <el-select v-model="cohortFilter" clearable filterable placeholder="比较组（自动）" style="width: 280px" @change="loadData">
          <el-option v-for="c in cohorts" :key="c.id" :label="cohortLabel(c)" :value="c.id" />
        </el-select>
        <el-select v-model="industry" clearable filterable placeholder="全部行业" style="width: 160px" @change="onDimChange">
          <el-option v-for="s in industries" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-select v-model="scene" clearable filterable placeholder="全部场景" style="width: 180px" @change="onDimChange">
          <el-option v-for="s in scenes" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
      </div>
      <p class="meta">
        比较组是同一套评测条件下的结果：同一数据版本、同一裁判、同一工具版本、同一指标权重、同一场景。条件不同的分数不能直接比高低。不选比较组时，展示结果最多的一组。
      </p>
      <p class="meta">
        榜单 {{ boardLabel }} · 当前比较组 {{ activeCohortLabel }} · 未入榜 {{ excludedTotal }}
      </p>
      <PageAsyncState
        v-if="['loading', 'error', 'forbidden', 'uncreated'].includes(listState)"
        :state="listState"
        :errorMessage="loadError"
      />
      <template v-else>
        <el-row v-if="podium.length" :gutter="12" class="block">
          <el-col v-for="(row, idx) in podium" :key="row.model_id + '-' + idx" :span="8">
            <el-card shadow="never" class="clickable" @click="toggleSelect(row)">
              <div class="stat-label">第 {{ formatRank(row.rank) }}</div>
              <div class="stat-value">{{ row.model_name }}</div>
              <p class="meta">{{ formatScore(row.norm_score) }} · {{ row.scene || '—' }} · {{ ((row.pass_rate || 0) * 100).toFixed(0) }}% 通过</p>
            </el-card>
          </el-col>
        </el-row>
        <el-table :data="items" stripe @row-click="toggleSelect">
          <template #empty>
            <EmptyState type="default" title="当前比较组暂无可比正式结果" description="完成正式评测后会自动出现在这一组里。" :show-action="false" />
          </template>
          <el-table-column width="40">
            <template #default="{ row }">
              <span class="sel-dot" :class="{ on: isSelected(row) }" />
            </template>
          </el-table-column>
          <el-table-column label="排名" width="80">
            <template #default="{ row }">{{ formatRank(row.rank) }}<span v-if="row.tied">=</span></template>
          </el-table-column>
          <el-table-column prop="model_name" label="模型" min-width="140" />
          <el-table-column prop="industry" label="行业" width="100">
            <template #default="{ row }">{{ row.industry || '—' }}</template>
          </el-table-column>
          <el-table-column prop="scene" label="场景" width="110">
            <template #default="{ row }">{{ row.scene || '—' }}</template>
          </el-table-column>
          <el-table-column label="平均分" width="100">
            <template #default="{ row }">{{ formatScore(row.avg_score) }}</template>
          </el-table-column>
          <el-table-column label="归一化" width="100">
            <template #default="{ row }">{{ formatScore(row.norm_score) }}</template>
          </el-table-column>
          <el-table-column v-if="board === 'value'" label="成本" width="100">
            <template #default="{ row }">{{ formatScore(row.cost) }}</template>
          </el-table-column>
          <el-table-column label="通过率" width="100">
            <template #default="{ row }">{{ row.pass_rate == null ? '—' : ((row.pass_rate || 0) * 100).toFixed(1) + '%' }}</template>
          </el-table-column>
          <el-table-column prop="task_name" label="来源任务" min-width="140" show-overflow-tooltip />
        </el-table>
      </template>
    </el-card>

    <el-row v-if="listState === 'success' || listState === 'empty'" :gutter="16">
      <el-col :md="14">
        <el-card shadow="never">
          <template #header>雷达对比（选 2–5 个模型 · 缺场景为 null）</template>
          <div ref="radarEl" class="radar" />
        </el-card>
      </el-col>
      <el-col v-if="userStore.hasPermission('leaderboard:edit')" :md="10">
        <el-card shadow="never">
          <template #header>成本表（可复算账单）</template>
          <el-table :data="costs" size="small" max-height="300">
            <el-table-column prop="model_name" label="模型" min-width="120" />
            <el-table-column label="Token/千" min-width="120">
              <template #default="{ row }">
                <el-input-number v-model="row.token_price_per_1k" :step="0.001" size="small" @change="saveCost(row)" />
              </template>
            </el-table-column>
            <el-table-column label="时延/秒" min-width="120">
              <template #default="{ row }">
                <el-input-number v-model="row.latency_price_per_sec" :step="0.001" size="small" @change="saveCost(row)" />
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import * as echarts from 'echarts'
import { leaderboardApi } from '@/api'
import { useUserStore } from '@/stores/user'
import EmptyState from '@/components/EmptyState.vue'
import PageAsyncState from '@/components/PageAsyncState.vue'
import { deriveAsyncState } from '@/utils/asyncState.js'

const userStore = useUserStore()
const items = ref([])
const costs = ref([])
const industry = ref('')
const scene = ref('')
const industries = ref([])
const scenes = ref([])
const board = ref('overall')
const stale = ref(false)
const cohortFilter = ref('')
const activeCohortId = ref('')
const cohorts = ref([])
const excludedTotal = ref(0)
const selected = ref([])
const radarEl = ref(null)
const loading = ref(false)
const loadError = ref('')
const createdOnce = ref(false)
let chart

const boards = [
  { value: 'overall', label: '综合' },
  { value: 'ability', label: '单项' },
  { value: 'special', label: '专项' },
  { value: 'value', label: '性价比' },
]

const boardLabel = computed(() => boards.find((b) => b.value === board.value)?.label || board.value)
const activeCohortLabel = computed(() => {
  const hit = cohorts.value.find((c) => c.id === activeCohortId.value)
  return hit ? cohortLabel(hit) : (activeCohortId.value || '—')
})

function cohortLabel(c) {
  const sceneName = scenes.value.find((s) => s.value === c.scene)?.label
  if (!sceneName || !c.scene) return c.label || c.id
  return String(c.label || c.id).replace(c.scene, sceneName)
}
const podium = computed(() => items.value.filter((r) => r.rank != null).slice(0, 3))
const listState = computed(() => deriveAsyncState({
  loading: loading.value && !createdOnce.value,
  error: loadError.value,
  forbidden: false,
  items: items.value,
  createdOnce: createdOnce.value,
}))

function loadErr(e, fallback) {
  const d = e?.response?.data
  const msg = d?.message || d?.detail || e?.message
  return typeof msg === 'string' && msg ? msg : fallback
}

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

function onDimChange() {
  cohortFilter.value = ''
  loadData()
}

async function loadData() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await leaderboardApi.list({
      board: board.value,
      industry: industry.value,
      scene: scene.value,
      cohort_id: cohortFilter.value,
    })
    items.value = res.items || []
    stale.value = !!res.stale
    scenes.value = res.scenes || scenes.value
    industries.value = res.industries || industries.value
    cohorts.value = res.cohorts || []
    activeCohortId.value = res.cohort_id || cohortFilter.value || ''
    excludedTotal.value = res.excluded_total || 0
    selected.value = []
    createdOnce.value = true
    await nextTick()
    await drawRadar()
  } catch (e) {
    loadError.value = loadErr(e, '榜单加载失败')
  } finally {
    loading.value = false
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

function themeColor(name, fallback) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
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
  const ink = themeColor('--text-secondary', '#64748b')
  const primary = themeColor('--el-color-primary', '#6366f1')
  chart.setOption({
    backgroundColor: 'transparent',
    textStyle: { color: ink },
    legend: { data: (data.series || []).map((s) => s.model_name), textStyle: { color: ink }, top: 0 },
    radar: {
      indicator: indicators.length ? indicators : [{ name: 'n/a', max: 1 }],
      axisName: { color: ink },
      splitLine: { lineStyle: { color: themeColor('--border-color', '#e2e8f0') } },
      splitArea: { areaStyle: { color: [themeColor('--bg-card', '#fff'), 'transparent'] } },
      axisLine: { lineStyle: { color: themeColor('--border-color', '#e2e8f0') } },
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
    color: [primary, ink],
  })
}

onMounted(async () => {
  await loadData()
  if (userStore.hasPermission('leaderboard:edit')) {
    try {
      const c = await leaderboardApi.costs()
      costs.value = c.items || []
    } catch (e) {
      if (!loadError.value) loadError.value = loadErr(e, '成本表加载失败')
    }
  }
  await nextTick()
  if (radarEl.value) chart = echarts.init(radarEl.value)
})
onUnmounted(() => chart?.dispose())
</script>

<style scoped>
.leaderboard-page { color: var(--text-primary); }
.page-header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.ops { display: flex; flex-wrap: wrap; gap: 8px; }
.block { margin-bottom: 16px; }
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
.meta { margin: 0 0 12px; font-size: 13px; color: var(--text-secondary); }
.stat-label { color: var(--text-secondary); font-size: 13px; }
.stat-value { margin-top: 8px; font-size: 18px; font-weight: 600; color: var(--text-primary); }
.clickable { cursor: pointer; background: var(--bg-card); }
.radar { height: 300px; }
.sel-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
  border: 1px solid var(--el-border-color);
  background: var(--bg-card);
}
.sel-dot.on {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
}
</style>
