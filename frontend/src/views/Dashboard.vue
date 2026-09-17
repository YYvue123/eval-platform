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
      <template #header>当前进度</template>
      <p>本仓库是评测平台骨架，从 llm-manager 复用了登录、权限、用户、通知和审计。</p>
      <p>后续将按文档接入：评测数据、被测模型注册、工具底座与批量评测。</p>
      <p v-if="stats.message" class="hint">{{ stats.message }}</p>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { dashboardApi } from '@/api'

const stats = ref({})

onMounted(async () => {
  try {
    stats.value = await dashboardApi.getStats()
  } catch (_) {
    stats.value = {}
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
