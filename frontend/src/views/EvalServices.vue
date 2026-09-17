<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">评测服务</h2>
        <p class="page-desc">需求提交 → 审核 → 执行 → 报告交付</p>
      </div>
      <el-button v-if="userStore.hasPermission('service:create')" type="primary" @click="showForm = true">提交需求</el-button>
    </div>
    <el-card>
      <el-table v-loading="loading" :data="items" stripe>
        <el-table-column prop="title" label="标题" min-width="180" />
        <el-table-column prop="industry" label="行业" width="100" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column prop="report_summary" label="交付摘要" min-width="220" show-overflow-tooltip />
        <el-table-column v-if="userStore.hasPermission('service:edit')" label="办理" width="280">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="setStatus(row, 'reviewing')">审核</el-button>
            <el-button link type="primary" size="small" @click="setStatus(row, 'approved')">通过</el-button>
            <el-button link type="success" size="small" @click="setStatus(row, 'delivered')">交付</el-button>
            <el-button link type="danger" size="small" @click="setStatus(row, 'rejected')">驳回</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showForm" title="提交评测需求" width="520px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="标题"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="行业"><el-input v-model="form.industry" /></el-form-item>
        <el-form-item label="需求"><el-input v-model="form.requirement" type="textarea" rows="4" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" @click="submit">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { servicesApi } from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const loading = ref(false)
const items = ref([])
const showForm = ref(false)
const form = ref({ title: '', industry: 'general', requirement: '' })

async function loadData() {
  loading.value = true
  try {
    const res = await servicesApi.list({ page_size: 50 })
    items.value = res.items || []
  } finally {
    loading.value = false
  }
}

async function submit() {
  await servicesApi.create(form.value)
  ElMessage.success('已提交')
  showForm.value = false
  loadData()
}

async function setStatus(row, status) {
  await servicesApi.updateStatus(row.id, { status })
  loadData()
}

onMounted(loadData)
</script>
