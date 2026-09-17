<template>
  <div v-loading="loading">
    <div class="page-header">
      <div>
        <h2 class="page-title">{{ detail.name || '数据集详情' }}</h2>
        <p class="page-desc">版本 {{ detail.current_version }} · {{ detail.data_count || 0 }} 条 · 质量 {{ detail.quality_status }}</p>
      </div>
      <div class="op-btns">
        <el-button v-if="userStore.hasPermission('quality:run')" @click="runQuality">质量检测</el-button>
        <el-button v-if="userStore.hasPermission('dataset:edit') && detail.status !== 'published'" type="success" @click="publish">发布</el-button>
        <el-button v-if="userStore.hasPermission('dataset:export')" @click="exportFile('jsonl')">导出 JSONL</el-button>
      </div>
    </div>

    <el-card class="block">
      <template #header>导入数据</template>
      <el-upload
        v-if="userStore.hasPermission('dataset:edit')"
        :auto-upload="false"
        :limit="1"
        accept=".json,.jsonl,.csv,.txt,.xlsx,.xls,.zip"
        :on-change="onFile"
      >
        <el-button type="primary">选择文件</el-button>
        <template #tip>
          <div class="el-upload__tip">支持 Excel / CSV / JSON / JSONL / TXT / ZIP，字段建议包含 input、reference</div>
        </template>
      </el-upload>
      <el-button v-if="file" type="primary" :loading="importing" style="margin-top: 12px" @click="doImport">开始导入</el-button>
    </el-card>

    <el-card class="block">
      <template #header>样本预览</template>
      <el-table :data="items" stripe max-height="420">
        <el-table-column prop="item_no" label="#" width="60" />
        <el-table-column prop="input_content" label="输入" min-width="220" show-overflow-tooltip />
        <el-table-column prop="reference_answer" label="参考答案" min-width="180" show-overflow-tooltip />
        <el-table-column prop="quality_flag" label="质量标记" width="110" />
      </el-table>
      <el-pagination
        v-if="itemTotal > itemPageSize"
        v-model:current-page="itemPage"
        :page-size="itemPageSize"
        :total="itemTotal"
        layout="total, prev, pager, next"
        class="pagination"
        @change="loadItems"
      />
    </el-card>

    <el-row :gutter="16">
      <el-col :md="12">
        <el-card>
          <template #header>版本</template>
          <el-table :data="detail.versions || []" size="small">
            <el-table-column prop="version_code" label="版本" width="80" />
            <el-table-column prop="data_count" label="条数" width="70" />
            <el-table-column prop="quality_status" label="质量" />
            <el-table-column prop="checksum" label="校验和" show-overflow-tooltip />
          </el-table>
        </el-card>
      </el-col>
      <el-col :md="12">
        <el-card>
          <template #header>操作日志</template>
          <el-table :data="detail.logs || []" size="small">
            <el-table-column prop="operation_type" label="操作" width="90" />
            <el-table-column prop="operation_desc" label="说明" />
            <el-table-column prop="operator" label="操作人" width="90" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { datasetsApi, qualityApi } from '@/api'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const userStore = useUserStore()
const loading = ref(false)
const detail = ref({})
const items = ref([])
const itemTotal = ref(0)
const itemPage = ref(1)
const itemPageSize = 20
const file = ref(null)
const importing = ref(false)

async function loadDetail() {
  loading.value = true
  try {
    detail.value = await datasetsApi.get(route.params.id)
    await loadItems()
  } finally {
    loading.value = false
  }
}

async function loadItems() {
  const res = await datasetsApi.items(route.params.id, { page: itemPage.value, page_size: itemPageSize })
  items.value = res.items || []
  itemTotal.value = res.total || 0
}

function onFile(uploadFile) {
  file.value = uploadFile.raw
}

async function doImport() {
  if (!file.value) return
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('file', file.value)
    fd.append('version_desc', '页面导入')
    const res = await datasetsApi.importFile(route.params.id, fd)
    ElMessage.success(`已导入 ${res.data_count} 条`)
    file.value = null
    await loadDetail()
  } finally {
    importing.value = false
  }
}

async function publish() {
  await datasetsApi.publish(route.params.id)
  ElMessage.success('已发布')
  loadDetail()
}

async function runQuality() {
  const res = await qualityApi.run({ dataset_id: route.params.id })
  ElMessage.success(`质量分 ${res.score}（${res.status}）`)
  loadDetail()
}

async function exportFile(fmt) {
  const blob = await datasetsApi.exportFile(route.params.id, { fmt })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${detail.value.name || 'dataset'}.${fmt}`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(loadDetail)
</script>

<style scoped>
.block { margin-bottom: 16px; }
.pagination { margin-top: 12px; justify-content: flex-end; }
</style>
