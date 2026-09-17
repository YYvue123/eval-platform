<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">模型榜单</h2>
        <p class="page-desc">综合 / 单项 / 专项 / 性价比。默认取各模型最近一次完整评测结果，分数归一化后排序。</p>
      </div>
      <div>
        <el-button v-if="userStore.hasPermission('leaderboard:edit')" @click="refresh">刷新快照</el-button>
        <el-button @click="exportCsv">导出 CSV</el-button>
      </div>
    </div>
    <el-alert v-if="stale" type="warning" :closable="false" title="数据更新异常，正在展示上次快照" style="margin-bottom: 12px" />
    <el-card>
      <div class="toolbar">
        <el-radio-group v-model="board" @change="loadData">
          <el-radio-button value="overall">综合得分</el-radio-button>
          <el-radio-button value="ability">单项能力</el-radio-button>
          <el-radio-button value="special">专项评测</el-radio-button>
          <el-radio-button value="value">性价比</el-radio-button>
        </el-radio-group>
        <el-input v-model="industry" placeholder="行业" clearable style="width: 140px; margin-left: 12px" @change="loadData" />
        <el-input v-model="scene" placeholder="场景" clearable style="width: 140px; margin-left: 8px" @change="loadData" />
      </div>
      <el-table :data="items" stripe @selection-change="onSelect">
        <el-table-column type="selection" width="42" />
        <el-table-column prop="rank" label="排名" width="70" />
        <el-table-column prop="model_name" label="模型" min-width="150" />
        <el-table-column prop="industry" label="行业" width="100" />
        <el-table-column prop="scene" label="场景" width="110" />
        <el-table-column prop="avg_score" label="平均分" width="100" />
        <el-table-column prop="norm_score" label="归一化" width="100" />
        <el-table-column v-if="board === 'value'" prop="cost" label="成本" width="100" />
        <el-table-column label="通过率" width="100">
          <template #default="{ row }">{{ ((row.pass_rate || 0) * 100).toFixed(1) }}%</template>
        </el-table-column>
        <el-table-column prop="task_name" label="来源任务" min-width="140" />
      </el-table>
    </el-card>
    <el-card style="margin-top: 16px">
      <template #header>雷达对比（选 2–5 个模型）</template>
      <div ref="radarEl" class="radar" />
    </el-card>
    <el-card v-if="userStore.hasPermission('leaderboard:edit')" style="margin-top: 16px">
      <template #header>成本价格表</template>
      <el-table :data="costs" size="small">
        <el-table-column prop="model_name" label="模型" />
        <el-table-column label="Token 单价/千">
          <template #default="{ row }">
            <el-input-number v-model="row.token_price_per_1k" :step="0.001" :precision="4" size="small" @change="saveCost(row)" />
          </template>
        </el-table-column>
        <el-table-column label="时延单价/秒">
          <template #default="{ row }">
            <el-input-number v-model="row.latency_price_per_sec" :step="0.001" :precision="4" size="small" @change="saveCost(row)" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
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
const selected = ref([])
const radarEl = ref(null)
let chart

function onSelect(rows) {
  selected.value = rows
  drawRadar()
}

async function loadData() {
  const res = await leaderboardApi.list({ board: board.value, industry: industry.value, scene: scene.value })
  items.value = res.items || []
  stale.value = !!res.stale
}

async function refresh() {
  await leaderboardApi.refresh({ board: board.value })
  ElMessage.success('已写入快照')
  loadData()
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
    gpu_hour_price: row.gpu_hour_price || 0
  })
}

async function drawRadar() {
  if (!chart || selected.value.length < 2) return
  const ids = selected.value.slice(0, 5).map((r) => r.model_id).join(',')
  const data = await leaderboardApi.radar({ model_ids: ids })
  chart.setOption({
    radar: { indicator: (data.scenes || []).map((s) => ({ name: s, max: 1 })) },
    series: [{
      type: 'radar',
      data: (data.series || []).map((s) => ({ name: s.model_name, value: s.values }))
    }]
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
.toolbar { display: flex; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.radar { height: 320px; }
</style>
