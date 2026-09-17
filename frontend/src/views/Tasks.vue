<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">评测任务</h2>
        <p class="page-desc">选择数据集、被测模型、提示词与打分工具，提交批量评测</p>
      </div>
      <el-button v-if="userStore.hasPermission('task:create')" type="primary" @click="openCreate">创建任务</el-button>
    </div>
    <el-card>
      <el-table v-loading="loading" :data="items" stripe>
        <template #empty>
          <EmptyState type="task" action-text="创建任务" :show-action="userStore.hasPermission('task:create')" @action="openCreate" />
        </template>
        <el-table-column prop="name" label="名称" min-width="160">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/tasks/${row.id}`)">{{ row.name }}</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="task_type" label="类型" width="110" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column label="进度" width="160">
          <template #default="{ row }">
            <el-progress :percentage="row.progress || 0" :stroke-width="8" />
          </template>
        </el-table-column>
        <el-table-column prop="pass_rate" label="通过率" width="90">
          <template #default="{ row }">{{ formatRate(row.pass_rate) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button v-if="userStore.hasPermission('task:run')" link type="primary" size="small" @click="run(row)">执行</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showForm" title="创建评测任务" width="560px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="任务名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.task_type">
            <el-option label="能力测试" value="capability" />
            <el-option label="安全可信" value="security" />
            <el-option label="场景应用" value="scene" />
            <el-option label="行业专项" value="industry" />
          </el-select>
        </el-form-item>
        <el-form-item label="行业"><el-input v-model="form.industry" placeholder="general / 医疗 / 政务" /></el-form-item>
        <el-form-item label="数据集">
          <el-select v-model="form.dataset_id" filterable style="width: 100%">
            <el-option v-for="d in datasets" :key="d.id" :label="`${d.name} (${d.data_count})`" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="被测模型">
          <el-select v-model="form.model_id" filterable style="width: 100%">
            <el-option v-for="m in models" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="提示词">
          <el-select v-model="form.prompt_id" clearable filterable style="width: 100%">
            <el-option v-for="p in prompts" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="打分工具">
          <el-select v-model="form.judge_resource_id" style="width: 100%">
            <el-option v-for="r in judges" :key="r.resource_id" :label="r.name" :value="r.resource_id" />
          </el-select>
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
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { datasetsApi, modelsApi, promptsApi, resourcesApi, tasksApi } from '@/api'
import { useUserStore } from '@/stores/user'
import EmptyState from '@/components/EmptyState.vue'

const userStore = useUserStore()
const router = useRouter()
const loading = ref(false)
const items = ref([])
const showForm = ref(false)
const submitting = ref(false)
const datasets = ref([])
const models = ref([])
const prompts = ref([])
const judges = ref([])
const form = ref({
  name: '', task_type: 'capability', industry: 'general',
  dataset_id: null, model_id: null, prompt_id: null, judge_resource_id: 'builtin/exact_match'
})

function formatRate(v) {
  return `${((v || 0) * 100).toFixed(1)}%`
}

async function loadData() {
  loading.value = true
  try {
    const res = await tasksApi.list({ page_size: 50 })
    items.value = res.items || []
  } finally {
    loading.value = false
  }
}

async function openCreate() {
  const [ds, ms, ps, rs] = await Promise.all([
    datasetsApi.list({ page_size: 100 }),
    modelsApi.list({ page_size: 100 }),
    promptsApi.list({ page_size: 100 }),
    resourcesApi.list({ resource_type: 'tool', page_size: 50 })
  ])
  datasets.value = ds.items || []
  models.value = ms.items || []
  prompts.value = ps.items || []
  judges.value = rs.items || []
  form.value = {
    name: '评测任务', task_type: 'capability', industry: 'general',
    dataset_id: datasets.value[0]?.id, model_id: models.value[0]?.id,
    prompt_id: prompts.value[0]?.id, judge_resource_id: 'builtin/exact_match'
  }
  showForm.value = true
}

async function submit() {
  submitting.value = true
  try {
    const created = await tasksApi.create(form.value)
    ElMessage.success('已创建')
    showForm.value = false
    router.push(`/tasks/${created.id}`)
  } finally {
    submitting.value = false
  }
}

async function run(row) {
  await tasksApi.run(row.id)
  ElMessage.success('已提交执行')
  loadData()
}

onMounted(loadData)
</script>
