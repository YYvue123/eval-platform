<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">任务模板库</h2>
        <p class="page-desc">语言/语音/视觉/多模态、场景与行业模板。每项绑定试点数据集、标尺与指标权重。</p>
      </div>
      <el-button v-if="userStore.hasPermission('task:create')" type="primary" @click="openCreate">新增模板</el-button>
    </div>
    <el-card>
      <el-radio-group v-model="category" style="margin-bottom: 12px" @change="loadData">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="capability">基础能力</el-radio-button>
        <el-radio-button value="scene">场景应用</el-radio-button>
        <el-radio-button value="industry">行业专项</el-radio-button>
      </el-radio-group>
      <PageAsyncState
        v-if="['loading', 'error', 'forbidden', 'uncreated'].includes(listState)"
        :state="listState"
        :errorMessage="loadError"
      />
      <template v-else>
        <el-table :data="items" stripe>
          <template #empty>
            <EmptyState type="default" title="暂无任务模板" description="可以手动新增，或调整分类后重试。" :show-action="userStore.hasPermission('task:create')" action-text="新增模板" @action="openCreate" />
          </template>
          <el-table-column prop="name" label="模板" min-width="160" />
          <el-table-column prop="category" label="分类" width="100" />
          <el-table-column prop="scene" label="场景" width="120" />
          <el-table-column prop="industry" label="行业" width="110" />
          <el-table-column prop="judge_resource_id" label="默认裁判" min-width="180" />
          <el-table-column prop="rubric" label="标尺" min-width="200" show-overflow-tooltip />
          <el-table-column label="操作" width="160">
            <template #default="{ row }">
              <el-button link type="primary" @click="openEdit(row)">{{ userStore.hasPermission('task:edit') ? '编辑' : '查看' }}</el-button>
              <el-button v-if="userStore.hasPermission('task:create')" link type="primary" @click="useTpl(row)">使用</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>

    <el-dialog v-model="showForm" :title="editing ? '编辑任务模板' : '新增任务模板'" width="720px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="编码">
          <el-input v-model="form.code" :disabled="editing" placeholder="如 scene.chat.custom" />
        </el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width: 100%">
            <el-option label="基础能力" value="capability" />
            <el-option label="场景应用" value="scene" />
            <el-option label="行业专项" value="industry" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务类型">
          <el-select v-model="form.task_type" style="width: 100%">
            <el-option label="能力测试" value="capability" />
            <el-option label="场景应用" value="scene" />
            <el-option label="行业专项" value="industry" />
          </el-select>
        </el-form-item>
        <el-form-item label="场景">
          <el-select v-model="form.scene" filterable allow-create style="width: 100%">
            <el-option v-for="s in scenes" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="行业">
          <el-select v-model="form.industry" filterable allow-create style="width: 100%">
            <el-option v-for="s in industries" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="默认裁判">
          <el-select v-model="form.judge_resource_id" filterable allow-create style="width: 100%">
            <el-option v-for="r in judges" :key="r.resource_id" :label="r.name" :value="r.resource_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="标尺"><el-input v-model="form.rubric" type="textarea" rows="3" /></el-form-item>
        <el-form-item label="默认提示词"><el-input v-model="form.default_prompt" type="textarea" rows="4" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" type="textarea" rows="2" /></el-form-item>
        <el-form-item label="指标权重">
          <el-input v-model="weightsText" type="textarea" rows="4" placeholder='JSON，如 {"accuracy": 1}' />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm = false">关闭</el-button>
        <el-button
          v-if="canSave"
          type="primary"
          :loading="saving"
          @click="save"
        >保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { resourcesApi, tasksApi } from '@/api'
import { useUserStore } from '@/stores/user'
import EmptyState from '@/components/EmptyState.vue'
import PageAsyncState from '@/components/PageAsyncState.vue'
import { deriveAsyncState } from '@/utils/asyncState.js'

const userStore = useUserStore()
const router = useRouter()
const items = ref([])
const category = ref('')
const loading = ref(false)
const loadError = ref('')
const createdOnce = ref(false)
const showForm = ref(false)
const editing = ref(false)
const saving = ref(false)
const weightsText = ref('{}')
const scenes = ref([])
const industries = ref([])
const judges = ref([])
const form = ref(emptyForm())

const listState = computed(() => deriveAsyncState({
  loading: loading.value && !createdOnce.value,
  error: loadError.value,
  forbidden: false,
  items: items.value,
  createdOnce: createdOnce.value,
}))

const canSave = computed(() => (editing.value
  ? userStore.hasPermission('task:edit')
  : userStore.hasPermission('task:create')))

function emptyForm() {
  return {
    code: '',
    name: '',
    category: 'scene',
    scene: 'chat',
    industry: 'general',
    task_type: 'capability',
    judge_resource_id: 'builtin/exact_match',
    rubric: '',
    default_prompt: '',
    description: '',
  }
}

function loadErr(e, fallback) {
  const d = e?.response?.data
  const msg = d?.message || d?.detail || e?.message
  return typeof msg === 'string' && msg ? msg : fallback
}

async function loadData() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await tasksApi.templates({ category: category.value })
    items.value = res.items || []
    createdOnce.value = true
  } catch (e) {
    loadError.value = loadErr(e, '任务模板加载失败')
  } finally {
    loading.value = false
  }
}

async function ensureOptions() {
  if (scenes.value.length && judges.value.length) return
  const [cat, rs] = await Promise.all([
    tasksApi.catalog(),
    resourcesApi.list({ resource_type: 'tool', page_size: 50 }),
  ])
  scenes.value = cat.scenes || []
  industries.value = cat.industries || []
  judges.value = rs.items || []
}

async function openCreate() {
  await ensureOptions()
  editing.value = false
  form.value = emptyForm()
  weightsText.value = '{}'
  showForm.value = true
}

async function openEdit(row) {
  await ensureOptions()
  editing.value = true
  form.value = {
    code: row.code,
    name: row.name || '',
    category: row.category || 'scene',
    scene: row.scene || 'chat',
    industry: row.industry || 'general',
    task_type: row.task_type || 'capability',
    judge_resource_id: row.judge_resource_id || 'builtin/exact_match',
    rubric: row.rubric || '',
    default_prompt: row.default_prompt || '',
    description: row.description || '',
  }
  weightsText.value = JSON.stringify(row.metric_weights || {}, null, 2)
  showForm.value = true
}

async function save() {
  if (!form.value.code.trim() || !form.value.name.trim()) {
    ElMessage.warning('请填写编码和名称')
    return
  }
  let metric_weights = {}
  try {
    metric_weights = weightsText.value.trim() ? JSON.parse(weightsText.value) : {}
  } catch {
    ElMessage.warning('指标权重需要是合法 JSON')
    return
  }
  if (metric_weights == null || typeof metric_weights !== 'object' || Array.isArray(metric_weights)) {
    ElMessage.warning('指标权重需要是 JSON 对象')
    return
  }
  saving.value = true
  try {
    const payload = { ...form.value, metric_weights }
    if (editing.value) await tasksApi.updateTemplate(form.value.code, payload)
    else await tasksApi.createTemplate(payload)
    ElMessage.success('已保存')
    showForm.value = false
    await loadData()
  } catch (e) {
    ElMessage.error(loadErr(e, '保存失败'))
  } finally {
    saving.value = false
  }
}

function useTpl(row) {
  router.push({ path: '/tasks', query: { template: row.code } })
}

onMounted(loadData)
</script>
