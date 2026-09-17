<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">数据质量</h2>
        <p class="page-desc">完整性、重复、格式异常检测与质量评分</p>
      </div>
    </div>
    <el-card>
      <el-table v-loading="loading" :data="items" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="dataset_id" label="数据集" width="90" />
        <el-table-column prop="score" label="得分" width="90" />
        <el-table-column prop="status" label="结论" width="100" />
        <el-table-column label="问题摘要" min-width="280">
          <template #default="{ row }">
            {{ summarize(row.report) }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { qualityApi } from '@/api'

const loading = ref(false)
const items = ref([])

function summarize(report) {
  const issues = report?.issues || {}
  return Object.entries(issues).map(([k, v]) => `${k}:${v}`).join('，') || '-'
}

onMounted(async () => {
  loading.value = true
  try {
    const res = await qualityApi.list({ page_size: 50 })
    items.value = res.items || []
  } finally {
    loading.value = false
  }
})
</script>
