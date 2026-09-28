<template>
  <div v-loading="loading">
    <div class="page-header">
      <div>
        <h2 class="page-title">{{ detail.name || '数据集详情' }}</h2>
        <p class="page-desc">
          版本 {{ detail.current_version }} · {{ detail.data_count || 0 }} 条 ·
          {{ statusLabel(detail.status) }} · 质量 {{ qualityLabel(detail.quality_status) }}
        </p>
      </div>
      <div class="op-btns">
        <el-button v-if="userStore.hasPermission('quality:run')" @click="runQuality">质量检测</el-button>
        <el-button
          v-if="userStore.hasPermission('dataset:edit') && ['draft', 'rejected'].includes(detail.status)"
          @click="submitReview"
        >提交审核</el-button>
        <el-button
          v-if="userStore.hasPermission('dataset:audit') && detail.status === 'pending'"
          type="success"
          @click="audit('approve')"
        >审核通过</el-button>
        <el-button
          v-if="userStore.hasPermission('dataset:audit') && detail.status === 'pending'"
          @click="audit('reject')"
        >退回</el-button>
        <el-button
          v-if="userStore.hasPermission('dataset:audit') && detail.status !== 'published'"
          type="success"
          :disabled="!canPublish"
          :title="canPublish ? '' : '需质检通过(passed)后才能发布'"
          @click="publish"
        >直接发布</el-button>
        <el-dropdown v-if="userStore.hasPermission('dataset:export')" @command="exportFile">
          <el-button>导出</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="jsonl">JSONL</el-dropdown-item>
              <el-dropdown-item command="csv">CSV</el-dropdown-item>
              <el-dropdown-item command="txt">TXT</el-dropdown-item>
              <el-dropdown-item command="xlsx">Excel</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
    <el-alert v-if="detail.review_comment" :title="`审核意见：${detail.review_comment}`" type="warning" show-icon class="block" />

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
          <div class="el-upload__tip">支持 Excel / CSV / JSON / JSONL / TXT / ZIP。选择后先确认字段映射再入库。</div>
        </template>
      </el-upload>
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
            <el-table-column label="" width="80">
              <template #default="{ row }">
                <el-button
                  v-if="userStore.hasPermission('dataset:edit') && row.id !== detail.current_version_id"
                  link
                  type="primary"
                  size="small"
                  @click="rollback(row)"
                >回滚</el-button>
              </template>
            </el-table-column>
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

    <el-dialog v-model="showMap" title="确认字段映射" width="640px">
      <el-alert v-if="preview.duplicate_checksum" title="该文件校验和已存在，继续导入将生成新版本。" type="warning" show-icon class="block" />
      <p>共解析 {{ preview.total || 0 }} 条。请确认源列到标准字段的映射。</p>
      <el-form label-width="120px">
        <el-form-item v-for="field in mapFields" :key="field.key" :label="field.label">
          <el-select v-model="mapping[field.key]" clearable placeholder="不映射" style="width: 100%">
            <el-option v-for="col in preview.columns || []" :key="col" :label="col" :value="col" />
          </el-select>
        </el-form-item>
      </el-form>
      <el-table :data="preview.sample || []" size="small" max-height="220">
        <el-table-column v-for="col in (preview.columns || []).slice(0, 6)" :key="col" :prop="col" :label="col" show-overflow-tooltip />
      </el-table>
      <template #footer>
        <el-button @click="showMap = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="doImport">确认导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
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
const showMap = ref(false)
const preview = ref({})
const mapping = ref({})
const mapFields = [
  { key: 'input_content', label: '输入' },
  { key: 'reference_answer', label: '参考答案' },
  { key: 'expected_output', label: '期望输出' },
  { key: 'task_requirement', label: '任务要求' },
  { key: 'difficulty_level', label: '难度' },
  { key: 'data_label', label: '标签' }
]

const canPublish = computed(() => ['passed', 'ok', 'good'].includes(detail.value?.quality_status))

function qualityLabel(s) {
  return ({
    unchecked: '未检测', checking: '检测中', passed: '合格', needs_clean: '需清洗',
    warning: '需清洗', review: '待复核', failed: '不合格', check_failed: '检测失败', cleaned: '已清洗'
  })[s] || s || '未检测'
}
function statusLabel(s) {
  return ({ draft: '草稿', pending: '待审核', published: '已发布', rejected: '已退回', disabled: '已停用', archived: '已归档' })[s] || s
}

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

async function onFile(uploadFile) {
  file.value = uploadFile.raw
  if (!file.value) return
  const fd = new FormData()
  fd.append('file', file.value)
  preview.value = await datasetsApi.preview(route.params.id, fd)
  mapping.value = { ...(preview.value.suggested_mapping || {}) }
  showMap.value = true
}

async function doImport() {
  if (!file.value) return
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('file', file.value)
    fd.append('version_desc', '页面导入')
    fd.append('field_mapping', JSON.stringify(mapping.value || {}))
    const res = await datasetsApi.importFile(route.params.id, fd)
    ElMessage.success(`已导入 ${res.data_count} 条`)
    file.value = null
    showMap.value = false
    await loadDetail()
  } finally {
    importing.value = false
  }
}

async function submitReview() {
  await datasetsApi.submit(route.params.id)
  ElMessage.success('已提交审核')
  loadDetail()
}

async function audit(action) {
  let comment = ''
  if (action === 'reject') {
    const { value } = await ElMessageBox.prompt('请填写退回原因', '审核退回', { inputPlaceholder: '原因' })
    comment = value
  }
  await datasetsApi.audit(route.params.id, { action, comment })
  ElMessage.success(action === 'approve' ? '已发布' : '已退回')
  loadDetail()
}

async function publish() {
  if (!canPublish.value) {
    ElMessage.warning('请先运行质量检测并达到「合格(passed)」后再发布')
    return
  }
  await datasetsApi.publish(route.params.id)
  ElMessage.success('已发布')
  loadDetail()
}

async function rollback(row) {
  await ElMessageBox.confirm(`回滚到 ${row.version_code}？当前版本仍会保留。`, '确认')
  await datasetsApi.rollback(route.params.id, row.id)
  ElMessage.success('已回滚')
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
  a.download = `${detail.value.name || 'dataset'}.${fmt === 'excel' ? 'xlsx' : fmt}`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(loadDetail)
</script>

<style scoped>
.block { margin-bottom: 16px; }
.pagination { margin-top: 12px; justify-content: flex-end; }
</style>
