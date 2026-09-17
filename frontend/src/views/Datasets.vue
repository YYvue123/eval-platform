<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">评测数据</h2>
        <p class="page-desc">导入、分类、版本化管理评测样本，供任务调度调用</p>
      </div>
      <el-button v-if="userStore.hasPermission('dataset:create')" type="primary" @click="openCreate">新增数据集</el-button>
    </div>
    <el-card>
      <div class="toolbar">
        <el-input v-model="search" placeholder="搜索名称/描述" clearable style="width: 220px" />
        <el-select v-model="status" placeholder="状态" clearable style="width: 140px">
          <el-option label="草稿" value="draft" />
          <el-option label="已发布" value="published" />
          <el-option label="已停用" value="disabled" />
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
        <el-table-column prop="quality_status" label="质量" width="100">
          <template #default="{ row }">
            <el-tag :type="qualityType(row.quality_status)" size="small">{{ row.quality_status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'published' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
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

function qualityType(s) {
  if (s === 'passed') return 'success'
  if (s === 'warning') return 'warning'
  if (s === 'failed') return 'danger'
  return 'info'
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
  await ElMessageBox.confirm(`删除数据集「${row.name}」？`, '确认')
  await datasetsApi.delete(row.id)
  ElMessage.success('已删除')
  loadData()
}

let timer
watch([search, status, domain], () => {
  clearTimeout(timer)
  timer = setTimeout(() => { page.value = 1; loadData() }, 250)
})
onMounted(loadData)
</script>

<style scoped>
.pagination { margin-top: 16px; justify-content: flex-end; }
</style>
