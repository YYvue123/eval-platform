<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">被测模型</h2>
        <p class="page-desc">注册在线推理接口或远程加密访问通道，支持 OpenAI 兼容 /v1/chat/completions</p>
      </div>
      <el-button v-if="userStore.hasPermission('model:create')" type="primary" @click="openCreate">注册模型</el-button>
    </div>
    <el-card>
      <div class="toolbar">
        <el-input v-model="search" placeholder="搜索模型" clearable style="width: 220px" />
      </div>
      <el-table v-loading="loading" :data="items" stripe>
        <template #empty>
          <EmptyState type="model" action-text="注册模型" :show-action="userStore.hasPermission('model:create')" @action="openCreate" />
        </template>
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="model_source" label="来源" width="100" />
        <el-table-column prop="access_mode" label="接入模式" width="140" />
        <el-table-column prop="health_status" label="健康" width="100" />
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <div class="op-btns">
              <el-button v-if="userStore.hasPermission('model:view')" link type="primary" size="small" @click="checkHealth(row)">探测</el-button>
              <el-button v-if="userStore.hasPermission('model:invoke')" link type="primary" size="small" @click="openInvoke(row)">试调用</el-button>
              <el-button v-if="userStore.hasPermission('model:edit')" link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
              <el-button v-if="userStore.hasPermission('model:delete')" link type="danger" size="small" @click="remove(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showForm" :title="form.id ? '编辑模型' : '注册模型'" width="640px">
      <el-form :model="form" label-width="120px">
        <el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="来源">
          <el-select v-model="form.model_source">
            <el-option label="外部企业" value="external" />
            <el-option label="内部开源" value="internal" />
          </el-select>
        </el-form-item>
        <el-form-item label="接入模式">
          <el-select v-model="form.access_mode">
            <el-option label="在线评测" value="online" />
            <el-option label="远程加密访问" value="remote_encrypted" />
          </el-select>
        </el-form-item>
        <el-form-item label="接口地址">
          <el-input v-model="form.api_url" placeholder="留空则使用本地 Mock；或填写 OpenAI 兼容 base URL" />
        </el-form-item>
        <el-form-item label="模型名"><el-input v-model="form.served_model_name" placeholder="chat/completions 中的 model 字段" /></el-form-item>
        <el-form-item label="API Key"><el-input v-model="form.api_key" type="password" show-password placeholder="不修改请留空" /></el-form-item>
        <el-form-item label="通道">
          <el-select v-model="form.channel_type">
            <el-option label="HTTPS / mTLS" value="https" />
            <el-option label="明文（仅联调）" value="plain" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" type="textarea" rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showInvoke" title="试调用" width="640px">
      <el-input v-model="invokePrompt" type="textarea" rows="4" placeholder="输入提示词" />
      <el-button type="primary" style="margin-top: 12px" :loading="invoking" @click="doInvoke">发送</el-button>
      <pre v-if="invokeResult" class="result">{{ invokeResult }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { modelsApi } from '@/api'
import { useUserStore } from '@/stores/user'
import EmptyState from '@/components/EmptyState.vue'

const userStore = useUserStore()
const loading = ref(false)
const items = ref([])
const search = ref('')
const showForm = ref(false)
const submitting = ref(false)
const form = ref({})
const showInvoke = ref(false)
const invokePrompt = ref('你好')
const invokeResult = ref('')
const invoking = ref(false)
const invokeId = ref(null)

function emptyForm() {
  return {
    name: '', model_source: 'external', access_mode: 'online', api_url: '',
    served_model_name: '', api_key: '', channel_type: 'https', description: ''
  }
}

async function loadData() {
  loading.value = true
  try {
    const res = await modelsApi.list({ search: search.value, page_size: 50 })
    items.value = res.items || []
  } finally {
    loading.value = false
  }
}

function openCreate() { form.value = emptyForm(); showForm.value = true }
function openEdit(row) { form.value = { ...row, api_key: '' }; showForm.value = true }

async function submit() {
  submitting.value = true
  try {
    if (form.value.id) await modelsApi.update(form.value.id, form.value)
    else await modelsApi.create(form.value)
    ElMessage.success('已保存')
    showForm.value = false
    loadData()
  } finally {
    submitting.value = false
  }
}

async function checkHealth(row) {
  const res = await modelsApi.health(row.id)
  ElMessage[res.ok ? 'success' : 'warning'](res.detail || res.status)
  loadData()
}

function openInvoke(row) {
  invokeId.value = row.id
  invokeResult.value = ''
  showInvoke.value = true
}

async function doInvoke() {
  invoking.value = true
  try {
    const res = await modelsApi.invoke(invokeId.value, { prompt: invokePrompt.value })
    invokeResult.value = res.output
  } finally {
    invoking.value = false
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`删除模型「${row.name}」？`, '确认')
  await modelsApi.delete(row.id)
  loadData()
}

let timer
watch(search, () => { clearTimeout(timer); timer = setTimeout(loadData, 250) })
onMounted(loadData)
</script>

<style scoped>
.result { margin-top: 12px; white-space: pre-wrap; background: var(--bg-page); padding: 12px; border-radius: 8px; }
</style>
