<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">数据质量</h2>
        <p class="page-desc">规则检测、问题工单与质量报告归档</p>
      </div>
    </div>
    <el-tabs v-model="tab">
      <el-tab-pane label="检测报告" name="reports">
        <el-card>
          <el-table v-loading="loading" :data="items" stripe>
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="dataset_id" label="数据集" width="90" />
            <el-table-column prop="score" label="得分" width="90" />
            <el-table-column prop="status" label="结论" width="110" />
            <el-table-column prop="issue_count" label="问题数" width="80" />
            <el-table-column label="问题摘要" min-width="240">
              <template #default="{ row }">
                {{ summarize(row.report) }}
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间" width="180" />
            <el-table-column label="操作" width="160">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openIssues(row)">问题</el-button>
                <el-button v-if="row.report_path" link type="primary" size="small" @click="download(row)">下载</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
      <el-tab-pane label="问题工单" name="issues">
        <el-card>
          <el-table :data="issues" stripe>
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="dataset_id" label="数据集" width="90" />
            <el-table-column prop="item_no" label="条目" width="70" />
            <el-table-column prop="rule_code" label="规则" width="160" />
            <el-table-column prop="description" label="说明" min-width="200" />
            <el-table-column prop="status" label="状态" width="90" />
            <el-table-column v-if="userStore.hasPermission('quality:edit')" label="处理" width="220">
              <template #default="{ row }">
                <el-button v-if="row.status === 'open'" link type="primary" size="small" @click="handle(row, 'ignore')">忽略</el-button>
                <el-button v-if="row.status === 'open'" link type="primary" size="small" @click="handle(row, 'review')">复核</el-button>
                <el-button v-if="row.status === 'open'" link type="success" size="small" @click="handle(row, 'fix')">修复并复检</el-button>
                <el-button v-if="row.status === 'open'" link type="danger" size="small" @click="handle(row, 'delete')">删除条目</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
      <el-tab-pane label="检测规则" name="rules">
        <el-card>
          <el-table :data="rules" stripe>
            <el-table-column prop="name" label="规则" min-width="140" />
            <el-table-column prop="code" label="编码" width="180" />
            <el-table-column prop="category" label="类别" width="110" />
            <el-table-column prop="severity" label="级别" width="90" />
            <el-table-column label="启用" width="90">
              <template #default="{ row }">
                <el-switch
                  v-model="row.enabled"
                  :disabled="!userStore.hasPermission('quality:edit')"
                  @change="toggleRule(row)"
                />
              </template>
            </el-table-column>
            <el-table-column prop="description" label="说明" min-width="200" />
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { qualityApi } from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const tab = ref('reports')
const loading = ref(false)
const items = ref([])
const issues = ref([])
const rules = ref([])

function summarize(report) {
  const issueMap = report?.issues || {}
  return Object.entries(issueMap).map(([k, v]) => `${k}:${v}`).join('，') || '-'
}

async function loadReports() {
  loading.value = true
  try {
    const res = await qualityApi.list({ page_size: 50 })
    items.value = res.items || []
  } finally {
    loading.value = false
  }
}

async function loadIssues(params = {}) {
  const res = await qualityApi.issues({ page_size: 50, ...params })
  issues.value = res.items || []
}

async function loadRules() {
  rules.value = await qualityApi.rules()
}

function openIssues(row) {
  tab.value = 'issues'
  loadIssues({ report_id: row.id })
}

async function handle(row, action) {
  const payload = { action, note: action, recheck: action === 'fix' || action === 'delete' }
  if (action === 'fix') {
    payload.input_content = row.description?.includes('输入') ? '已修复输入' : undefined
  }
  const res = await qualityApi.handleIssue(row.id, payload)
  if (res.recheck) {
    ElMessage.success(`已修复并复检：${res.recheck.status} / ${res.recheck.score}`)
    loadReports()
  } else {
    ElMessage.success('已处理')
  }
  loadIssues({ report_id: row.report_id })
}

async function toggleRule(row) {
  await qualityApi.updateRule(row.id, { enabled: row.enabled })
}

async function download(row) {
  const blob = await qualityApi.download(row.id)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `quality-${row.id}.json`
  a.click()
  URL.revokeObjectURL(url)
}

watch(tab, (v) => {
  if (v === 'issues' && !issues.value.length) loadIssues()
  if (v === 'rules' && !rules.value.length) loadRules()
})

onMounted(loadReports)
</script>
