<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">评测数据</h2>
        <p class="page-desc">导入、分类、审核与版本化管理评测样本</p>
      </div>
      <div class="op-btns">
        <el-button v-if="userStore.hasPermission('dataset:edit')" @click="showTags = true">标签管理</el-button>
        <el-button v-if="userStore.hasPermission('dataset:create')" type="primary" @click="openCreate">新增数据集</el-button>
      </div>
    </div>
    <el-card>
      <div class="toolbar">
        <el-input v-model="search" placeholder="搜索名称/描述" clearable style="width: 220px" />
        <el-select v-model="status" placeholder="状态" clearable style="width: 140px">
          <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-select v-model="domain" placeholder="领域" clearable style="width: 140px">
          <el-option v-for="d in domains" :key="d" :label="d" :value="d" />
        </el-select>
      </div>
      <el-table v-loading="loading" :data="items" stripe>
        <template #empty>
          <EmptyState type="dataset" action-text="新增数据集" :show-action="userStore.hasPermission('dataset:create')" @action="openCreate" />
        </template>
        <el-table-column prop="name" label="名称" min-width="160">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/datasets/${row.id}`)">{{ row.name }}</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="task_type" label="任务类型" width="110" />
        <el-table-column prop="domain_type" label="领域" width="100" />
        <el-table-column prop="data_count" label="条数" width="80" />
        <el-table-column prop="current_version" label="版本" width="90" />
        <el-table-column prop="quality_status" label="质量" width="110">
          <template #default="{ row }">
            <el-tag :type="qualityType(row.quality_status)" size="small">{{ qualityLabel(row.quality_status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <div class="op-btns">
              <el-button link type="primary" size="small" @click="$router.push(`/datasets/${row.id}`)">详情</el-button>
              <el-button v-if="userStore.hasPermission('dataset:delete')" link type="danger" size="small" @click="remove(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-if="total > pageSize"
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @change="loadData"
      />
    </el-card>

    <el-dialog v-model="showForm" title="新增数据集" width="520px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="任务类型">
          <el-input v-model="form.task_type" placeholder="qa / summary / safety" />
        </el-form-item>
        <el-form-item label="领域">
          <el-input v-model="form.domain_type" placeholder="general / 医疗 / 政务" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showTags" title="分类标签" width="640px">
      <el-form inline>
        <el-form-item label="名称">
          <el-input v-model="tagForm.name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="tagForm.tag_type" style="width: 120px">
            <el-option label="自定义" value="custom" />
            <el-option label="领域" value="domain" />
            <el-option label="任务" value="task" />
            <el-option label="系统" value="system" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="createTag">新增标签</el-button>
        </el-form-item>
      </el-form>
      <el-table :data="tags" size="small">
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="tag_type" label="类型" width="90" />
        <el-table-column prop="use_count" label="使用" width="70" />
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button v-if="row.status !== 'disabled'" link type="danger" size="small" @click="disableTag(row)">停用</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { datasetsApi } from '@/api'
import { useUserStore } from '@/stores/user'
import EmptyState from '@/components/EmptyState.vue'

const userStore = useUserStore()
const router = useRouter()
const domains = ['general', '医疗', '政务', '金融', '教育', '工业']
const statusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'pending', label: '待审核' },
  { value: 'published', label: '已发布' },
  { value: 'rejected', label: '已退回' },
  { value: 'disabled', label: '已停用' },
  { value: 'archived', label: '已归档' }
]
const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const search = ref('')
const status = ref('')
const domain = ref('')
const showForm = ref(false)
const submitting = ref(false)
const form = ref({ name: '', task_type: 'qa', domain_type: 'general', description: '' })
const showTags = ref(false)
const tags = ref([])
const tagForm = ref({ name: '', tag_type: 'custom' })

function qualityType(s) {
  if (s === 'passed') return 'success'
  if (s === 'needs_clean' || s === 'warning' || s === 'review') return 'warning'
  if (s === 'failed' || s === 'check_failed') return 'danger'
  return 'info'
}
function qualityLabel(s) {
  return ({
    unchecked: '未检测', checking: '检测中', passed: '合格', needs_clean: '需清洗',
    warning: '需清洗', review: '待复核', failed: '不合格', check_failed: '检测失败', cleaned: '已清洗'
  })[s] || s
}
function statusType(s) {
  if (s === 'published') return 'success'
  if (s === 'pending') return 'warning'
  if (s === 'rejected') return 'danger'
  return 'info'
}
function statusLabel(s) {
  return ({ draft: '草稿', pending: '待审核', published: '已发布', rejected: '已退回', disabled: '已停用', archived: '已归档', deleted: '已删除' })[s] || s
}

async function loadData() {
  loading.value = true
  try {
    const res = await datasetsApi.list({
      page: page.value,
      page_size: pageSize.value,
      search: search.value,
      status: status.value,
      domain_type: domain.value
    })
    items.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

async function loadTags() {
  tags.value = await datasetsApi.tags()
}

function openCreate() {
  form.value = { name: '', task_type: 'qa', domain_type: 'general', description: '' }
  showForm.value = true
}

async function submit() {
  if (!form.value.name.trim()) return ElMessage.warning('请填写名称')
  submitting.value = true
  try {
    const created = await datasetsApi.create(form.value)
    ElMessage.success('已创建，请继续导入数据')
    showForm.value = false
    router.push(`/datasets/${created.id}`)
  } finally {
    submitting.value = false
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`将逻辑删除数据集「${row.name}」。已被任务占用时条目仍保留以便追溯。`, '确认')
  await datasetsApi.delete(row.id)
  ElMessage.success('已删除')
  loadData()
}

async function createTag() {
  if (!tagForm.value.name.trim()) return ElMessage.warning('请填写标签名')
  await datasetsApi.createTag(tagForm.value)
  tagForm.value = { name: '', tag_type: 'custom' }
  loadTags()
}

async function disableTag(row) {
  await datasetsApi.deleteTag(row.id)
  loadTags()
}

let timer
watch([search, status, domain], () => {
  clearTimeout(timer)
  timer = setTimeout(() => { page.value = 1; loadData() }, 250)
})
watch(showTags, (v) => { if (v) loadTags() })
onMounted(loadData)
</script>

<style scoped>
.pagination { margin-top: 16px; justify-content: flex-end; }
</style>
