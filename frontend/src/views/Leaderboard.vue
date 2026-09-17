<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">模型榜单</h2>
        <p class="page-desc">按各模型最近一次成功评测的平均分与通过率排名</p>
      </div>
    </div>
    <el-card>
      <div class="toolbar">
        <el-input v-model="industry" placeholder="行业筛选" clearable style="width: 180px" @change="loadData" />
      </div>
      <el-table :data="items" stripe>
        <el-table-column prop="rank" label="排名" width="80" />
        <el-table-column prop="model_name" label="模型" min-width="160" />
        <el-table-column prop="industry" label="行业" width="120" />
        <el-table-column prop="avg_score" label="平均分" width="110" />
        <el-table-column label="通过率" width="110">
          <template #default="{ row }">{{ ((row.pass_rate || 0) * 100).toFixed(1) }}%</template>
        </el-table-column>
        <el-table-column prop="task_name" label="来源任务" min-width="160" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { leaderboardApi } from '@/api'

const items = ref([])
const industry = ref('')

async function loadData() {
  const res = await leaderboardApi.list({ industry: industry.value })
  items.value = res.items || []
}

onMounted(loadData)
</script>
