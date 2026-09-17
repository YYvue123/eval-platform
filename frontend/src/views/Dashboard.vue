<template>
  <div class="dashboard-page">
    <el-row :gutter="16">
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">用户数</div>
          <div class="stat-value">{{ stats.user_count ?? '-' }}</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">评测数据集</div>
          <div class="stat-value">{{ stats.dataset_count ?? 0 }}</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">被测模型</div>
          <div class="stat-value">{{ stats.model_count ?? 0 }}</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">评测任务</div>
          <div class="stat-value">{{ stats.task_count ?? 0 }}</div>
        </el-card>
      </el-col>
    </el-row>
    <el-card shadow="never" class="intro-card">
      <template #header>最近任务</template>
      <el-table v-if="workbench.recent?.length" :data="workbench.recent" size="small">
        <el-table-column prop="name" label="任务" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column label="通过率" width="110">
          <template #default="{ row }">{{ ((row.pass_rate || 0) * 100).toFixed(1) }}%</template>
        </el-table-column>
        <el-table-column label="" width="90">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/tasks/${row.id}`)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p v-else class="hint">还没有评测任务。从「评测数据」导入样本，注册被测模型后即可创建任务。</p>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { dashboardApi } from '@/api'

const stats = ref({})
const workbench = ref({})

onMounted(async () => {
  try {
    stats.value = await dashboardApi.getStats()
    workbench.value = await dashboardApi.getWorkbench()
  } catch (_) {
    stats.value = {}
    workbench.value = {}
  }
})
</script>

<style scoped>
.dashboard-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.stat-card {
  margin-bottom: 16px;
}
.stat-label {
  color: var(--text-secondary);
  font-size: 13px;
}
.stat-value {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 600;
}
.intro-card p {
  margin: 0 0 8px;
  line-height: 1.6;
}
.hint {
  color: var(--text-secondary);
}
</style>
