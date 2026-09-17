<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">提示词工程</h2>
        <p class="page-desc">用 {{variable}} 引用样本字段，保证评测输入口径一致</p>
      </div>
      <el-button v-if="userStore.hasPermission('prompt:create')" type="primary" @click="openCreate">新增模板</el-button>
    </div>
    <el-card>
      <el-table v-loading="loading" :data="items" stripe>
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="applicable_task" label="任务" width="100" />
        <el-table-column prop="current_version" label="版本" width="90" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="userStore.hasPermission('prompt:publish')" link type="success" size="small" @click="publish(row)">发布</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showForm" :title="form.id ? '编辑提示词' : '新增提示词'" width="720px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="适用任务"><el-input v-model="form.applicable_task" /></el-form-item>
        <el-form-item label="正文">
          <el-input v-model="form.prompt_content" type="textarea" rows="8" placeholder="请根据以下内容作答：{{input}}" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="preview">预览填充</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
      <pre v-if="previewText" class="result">{{ previewText }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { promptsApi } from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const loading = ref(false)
const items = ref([])
const showForm = ref(false)
const submitting = ref(false)
const previewText = ref('')
const form = ref({ name: '', applicable_task: 'qa', prompt_content: '请回答：{{input}}' })

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
  form.value = { name: '', applicable_task: 'qa', prompt_content: '请回答：{{input}}' }
  previewText.value = ''
  showForm.value = true
}

async function openEdit(row) {
  const detail = await promptsApi.get(row.id)
  form.value = { ...detail }
  previewText.value = ''
  showForm.value = true
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

onMounted(loadData)
</script>

<style scoped>
.result { margin-top: 12px; white-space: pre-wrap; background: var(--bg-page); padding: 12px; border-radius: 8px; }
</style>
