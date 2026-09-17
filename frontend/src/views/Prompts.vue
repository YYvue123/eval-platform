<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">提示词工程</h2>
        <p class="page-desc">模板、变量、审核发布、规则生成/优化与效果测试</p>
      </div>
      <div class="op-btns">
        <el-button v-if="userStore.hasPermission('prompt:create')" @click="openGenerate">自动生成</el-button>
        <el-button v-if="userStore.hasPermission('prompt:create')" type="primary" @click="openCreate">新增模板</el-button>
      </div>
    </div>
    <el-card>
      <el-table v-loading="loading" :data="items" stripe>
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="applicable_task" label="任务" width="100" />
        <el-table-column prop="current_version" label="版本" width="90" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column label="操作" width="320">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" size="small" @click="openDetail(row)">详情</el-button>
            <el-button v-if="userStore.hasPermission('prompt:edit') && ['draft','rejected'].includes(row.status)" link size="small" @click="submitReview(row)">提交审核</el-button>
            <el-button v-if="userStore.hasPermission('prompt:audit') && row.status === 'pending'" link type="success" size="small" @click="audit(row, 'approve')">通过</el-button>
            <el-button v-if="userStore.hasPermission('prompt:publish')" link type="success" size="small" @click="publish(row)">发布</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showForm" :title="form.id ? '编辑提示词' : '新增提示词'" width="760px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="适用任务">
          <el-select v-model="form.applicable_task" style="width: 100%">
            <el-option v-for="t in taskTypes" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-select v-model="form.tags" multiple filterable allow-create default-first-option style="width: 100%" />
        </el-form-item>
        <el-form-item label="正文">
          <el-input v-model="form.prompt_content" type="textarea" rows="8" placeholder="请根据以下内容作答：{{input}}" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="preview">预览填充</el-button>
        <el-button v-if="form.id && userStore.hasPermission('prompt:edit')" @click="optimize">优化并出新版本</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
      <pre v-if="previewText" class="result">{{ previewText }}</pre>
    </el-dialog>

    <el-dialog v-model="showGen" title="按任务类型生成草稿" width="560px">
      <el-form label-width="100px">
        <el-form-item label="任务类型">
          <el-select v-model="gen.task_type" style="width: 100%">
            <el-option v-for="t in taskTypes" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="指标">
          <el-input v-model="gen.metricsText" placeholder="逗号分隔，如 准确率,完成率" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" @click="doGenerate">生成到编辑框</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="showDetail" title="提示词详情" size="560px">
      <template v-if="detail.id">
        <p>状态 {{ detail.status }} · 占用任务 {{ detail.in_use || 0 }}</p>
        <el-alert v-if="detail.review_comment" :title="detail.review_comment" type="warning" show-icon />
        <div class="op-btns" style="margin: 8px 0">
          <el-button v-if="userStore.hasPermission('prompt:create')" size="small" @click="copyOne">复制</el-button>
          <el-button v-if="userStore.hasPermission('prompt:delete')" size="small" type="danger" @click="removeOne">删除</el-button>
        </div>
        <h4>效果分析</h4>
        <p v-if="stats">任务 {{ stats.task_count }} · 平均分 {{ stats.avg_score }} · 稳定性 {{ stats.stability }} · 调用 {{ stats.call_count }}</p>
        <h4>效果测试</h4>
        <el-form inline>
          <el-form-item><el-select v-model="testForm.dataset_id" placeholder="数据集" filterable style="width: 160px">
            <el-option v-for="d in datasets" :key="d.id" :label="d.name" :value="d.id" />
          </el-select></el-form-item>
          <el-form-item><el-select v-model="testForm.model_id" placeholder="模型" filterable style="width: 140px">
            <el-option v-for="m in models" :key="m.id" :label="m.name" :value="m.id" />
          </el-select></el-form-item>
          <el-form-item><el-button type="primary" :loading="testing" @click="runTest">跑 5 条</el-button></el-form-item>
        </el-form>
        <el-table :data="tests" size="small">
          <el-table-column prop="avg_score" label="得分" width="80" />
          <el-table-column prop="compare_avg_score" label="对照" width="80" />
          <el-table-column prop="sample_count" label="样本" width="70" />
          <el-table-column prop="created_at" label="时间" />
        </el-table>
        <h4>版本</h4>
        <el-table :data="detail.versions || []" size="small">
          <el-table-column prop="version_code" label="版本" width="80" />
          <el-table-column prop="change_desc" label="说明" />
          <el-table-column label="" width="80">
            <template #default="{ row }">
              <el-button v-if="row.id !== detail.current_version_id" link type="primary" size="small" @click="restore(row)">恢复</el-button>
            </template>
          </el-table-column>
        </el-table>
        <h4>调用日志</h4>
        <el-table :data="logs" size="small">
          <el-table-column prop="operation" label="操作" width="80" />
          <el-table-column prop="operator" label="操作人" width="90" />
          <el-table-column prop="task_id" label="任务" width="70" />
          <el-table-column prop="created_at" label="时间" />
        </el-table>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { datasetsApi, modelsApi, promptsApi } from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const taskTypes = ['qa', 'summary', 'safety', 'code', 'rag']
const loading = ref(false)
const items = ref([])
const showForm = ref(false)
const submitting = ref(false)
const previewText = ref('')
const form = ref({ name: '', applicable_task: 'qa', prompt_content: '请回答：{{input}}', tags: [] })
const showGen = ref(false)
const gen = ref({ task_type: 'qa', metricsText: '' })
const showDetail = ref(false)
const detail = ref({})
const stats = ref(null)
const tests = ref([])
const logs = ref([])
const datasets = ref([])
const models = ref([])
const testing = ref(false)
const testForm = ref({ dataset_id: null, model_id: null })

async function loadData() {
  loading.value = true
  try {
    const res = await promptsApi.list({ page_size: 50 })
    items.value = res.items || []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.value = { name: '', applicable_task: 'qa', prompt_content: '请回答：{{input}}', tags: [] }
  previewText.value = ''
  showForm.value = true
}

function openGenerate() {
  gen.value = { task_type: 'qa', metricsText: '' }
  showGen.value = true
}

async function doGenerate() {
  const metrics = gen.value.metricsText.split(/[,，]/).map((s) => s.trim()).filter(Boolean)
  const res = await promptsApi.generate({ task_type: gen.value.task_type, metrics })
  form.value = {
    name: `${gen.value.task_type}-模板`,
    applicable_task: res.applicable_task,
    prompt_content: res.prompt_content,
    tags: []
  }
  showGen.value = false
  showForm.value = true
}

async function openEdit(row) {
  const d = await promptsApi.get(row.id)
  form.value = { ...d, tags: d.tags || [] }
  previewText.value = ''
  showForm.value = true
}

async function openDetail(row) {
  detail.value = await promptsApi.get(row.id)
  stats.value = await promptsApi.stats(row.id)
  tests.value = await promptsApi.tests(row.id)
  logs.value = await promptsApi.logs(row.id)
  const [ds, ms] = await Promise.all([
    datasetsApi.list({ page_size: 50 }),
    modelsApi.list({ page_size: 50 })
  ])
  datasets.value = ds.items || []
  models.value = ms.items || []
  testForm.value = { dataset_id: datasets.value[0]?.id, model_id: models.value[0]?.id }
  showDetail.value = true
}

async function submit() {
  submitting.value = true
  try {
    if (form.value.id) await promptsApi.update(form.value.id, form.value)
    else await promptsApi.create(form.value)
    ElMessage.success('已保存')
    showForm.value = false
    loadData()
  } finally {
    submitting.value = false
  }
}

async function optimize() {
  const res = await promptsApi.optimize(form.value.id)
  ElMessage.success((res.suggestions || []).join('；') || '已分析')
  if (res.optimized) form.value.prompt_content = res.optimized
  loadData()
}

async function submitReview(row) {
  await promptsApi.submit(row.id)
  ElMessage.success('已提交审核')
  loadData()
}

async function audit(row, action) {
  let comment = ''
  if (action === 'reject') {
    const box = await ElMessageBox.prompt('退回原因', '审核')
    comment = box.value
  }
  await promptsApi.audit(row.id, { action, comment })
  loadData()
}

async function publish(row) {
  await promptsApi.publish(row.id)
  ElMessage.success('已发布')
  loadData()
}

async function preview() {
  if (form.value.id) {
    const res = await promptsApi.preview(form.value.id, {
      prompt_content: form.value.prompt_content,
      values: { input: '示例问题：首都是哪里？' }
    })
    previewText.value = res.rendered
  } else {
    previewText.value = (form.value.prompt_content || '').replaceAll('{{input}}', '示例问题：首都是哪里？')
  }
}

async function runTest() {
  if (!testForm.value.dataset_id || !testForm.value.model_id) return ElMessage.warning('请选择数据集和模型')
  testing.value = true
  try {
    const res = await promptsApi.runTest(detail.value.id, { ...testForm.value, limit: 5 })
    ElMessage.success(`测试均分 ${res.avg_score}`)
    tests.value = await promptsApi.tests(detail.value.id)
    stats.value = await promptsApi.stats(detail.value.id)
  } finally {
    testing.value = false
  }
}

async function restore(row) {
  await promptsApi.restore(detail.value.id, row.id)
  detail.value = await promptsApi.get(detail.value.id)
  loadData()
}

async function copyOne() {
  await promptsApi.copy(detail.value.id)
  ElMessage.success('已复制')
  showDetail.value = false
  loadData()
}

async function removeOne() {
  await ElMessageBox.confirm('逻辑删除该提示词？被任务占用时仍可追溯。', '确认')
  await promptsApi.delete(detail.value.id)
  showDetail.value = false
  loadData()
}

onMounted(loadData)
</script>

<style scoped>
.result { margin-top: 12px; white-space: pre-wrap; background: var(--bg-page); padding: 12px; border-radius: 8px; }
h4 { margin: 16px 0 8px; }
</style>
