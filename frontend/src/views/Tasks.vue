<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">评测任务</h2>
        <p class="page-desc">队列调度、依赖编排与模板化评测。正式任务可走审核；试跑可直接执行。</p>
      </div>
      <el-button v-if="userStore.hasPermission('task:create')" type="primary" @click="openCreate()">创建任务</el-button>
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
        <el-table-column prop="task_type" label="类型" width="100" />
        <el-table-column prop="scene" label="场景" width="110" />
        <el-table-column prop="industry" label="行业" width="90" />
        <el-table-column prop="priority" label="优先级" width="80" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            {{ row.status }}{{ row.trial_run ? '（试跑）' : '' }}
          </template>
        </el-table-column>
        <el-table-column label="进度" width="140">
          <template #default="{ row }">
            <el-progress :percentage="row.progress || 0" :stroke-width="8" />
          </template>
        </el-table-column>
        <el-table-column prop="pass_rate" label="通过率" width="90">
          <template #default="{ row }">{{ formatRate(row.pass_rate) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="240">
          <template #default="{ row }">
            <el-button v-if="userStore.hasPermission('task:edit') && row.status === 'draft'" link type="primary" size="small" @click="submitReview(row)">提交审核</el-button>
            <el-button v-if="userStore.hasPermission('task:audit') && row.status === 'pending_review'" link type="primary" size="small" @click="audit(row, true)">通过</el-button>
            <el-button v-if="userStore.hasPermission('task:run')" link type="primary" size="small" @click="run(row)">执行</el-button>
            <el-button v-if="userStore.hasPermission('task:run') && ['queued','running','draft','pending_review'].includes(row.status)" link size="small" @click="cancel(row)">取消</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showForm" title="创建评测任务" width="620px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="任务名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="任务模板">
          <el-select v-model="form.template_code" clearable filterable style="width: 100%" @change="applyTemplate">
            <el-option v-for="t in templates" :key="t.code" :label="t.name" :value="t.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.task_type">
            <el-option label="能力测试" value="capability" />
            <el-option label="安全可信" value="security" />
            <el-option label="场景应用" value="scene" />
            <el-option label="行业专项" value="industry" />
          </el-select>
        </el-form-item>
        <el-form-item label="场景">
          <el-select v-model="form.scene" filterable style="width: 100%">
            <el-option v-for="s in scenes" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="行业">
          <el-select v-model="form.industry" filterable style="width: 100%">
            <el-option v-for="s in industries" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级"><el-input-number v-model="form.priority" :min="1" :max="10" /></el-form-item>
        <el-form-item label="依赖任务">
          <el-select v-model="form.depends_on_id" clearable filterable style="width: 100%">
            <el-option v-for="t in items" :key="t.id" :label="`${t.id} ${t.name}`" :value="t.id" />
          </el-select>
        </el-form-item>
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
        <el-form-item label="仅测试">
          <el-switch v-model="form.trial_run" />
          <span class="hint">质量不合格数据只能走试跑，不能进入正式评测</span>
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
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { datasetsApi, modelsApi, promptsApi, resourcesApi, tasksApi } from '@/api'
import { useUserStore } from '@/stores/user'
import EmptyState from '@/components/EmptyState.vue'

const userStore = useUserStore()
const router = useRouter()
const route = useRoute()
const loading = ref(false)
const items = ref([])
const showForm = ref(false)
const submitting = ref(false)
const datasets = ref([])
const models = ref([])
const prompts = ref([])
const judges = ref([])
const templates = ref([])
const scenes = ref([])
const industries = ref([])
const form = ref(emptyForm())

function emptyForm() {
  return {
    name: '', task_type: 'capability', scene: 'chat', industry: 'general',
    dataset_id: null, model_id: null, prompt_id: null, judge_resource_id: 'builtin/exact_match',
    trial_run: false, template_code: '', priority: 5, depends_on_id: null
  }
}

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

function applyTemplate(code) {
  const t = templates.value.find((x) => x.code === code)
  if (!t) return
  form.value.task_type = t.task_type
  form.value.scene = t.scene
  form.value.industry = t.industry
  form.value.judge_resource_id = t.judge_resource_id
  if (t.pack_dataset_id) form.value.dataset_id = t.pack_dataset_id
  if (!form.value.name || form.value.name === '评测任务') form.value.name = t.name
}

async function openCreate(presetCode) {
  const [ds, ms, ps, rs, cat, tpls] = await Promise.all([
    datasetsApi.list({ page_size: 200 }),
    modelsApi.list({ page_size: 100 }),
    promptsApi.list({ page_size: 100 }),
    resourcesApi.list({ resource_type: 'tool', page_size: 50 }),
    tasksApi.catalog(),
    tasksApi.templates()
  ])
  datasets.value = ds.items || []
  models.value = ms.items || []
  prompts.value = ps.items || []
  judges.value = rs.items || []
  scenes.value = cat.scenes || []
  industries.value = cat.industries || []
  templates.value = tpls.items || []
  form.value = {
    ...emptyForm(),
    name: '评测任务',
    dataset_id: datasets.value[0]?.id,
    model_id: models.value[0]?.id,
    prompt_id: prompts.value[0]?.id,
    template_code: presetCode || route.query.template || ''
  }
  if (form.value.template_code) applyTemplate(form.value.template_code)
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

async function cancel(row) {
  await tasksApi.cancel(row.id)
  ElMessage.success('已取消')
  loadData()
}

async function submitReview(row) {
  await tasksApi.submit(row.id)
  ElMessage.success('已提交审核')
  loadData()
}

async function audit(row, approved) {
  await tasksApi.audit(row.id, { approved })
  ElMessage.success(approved ? '已通过' : '已退回')
  loadData()
}

onMounted(async () => {
  await loadData()
  if (route.query.template) openCreate(route.query.template)
})
</script>

<style scoped>
.hint { margin-left: 8px; color: var(--el-text-color-secondary); font-size: 12px; }
</style>
