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
          <PageAsyncState
            v-if="['loading', 'error', 'forbidden', 'uncreated'].includes(reportState)"
            :state="reportState"
            :errorMessage="loadError"
          />
          <template v-else>
            <el-table v-loading="loading" :data="items" stripe>
              <template #empty>
                <EmptyState type="default" title="暂无检测报告" description="完成一次质检后可在此查看归档" />
              </template>
              <el-table-column prop="id" label="ID" width="70" />
              <el-table-column label="数据集" min-width="160" show-overflow-tooltip>
                <template #default="{ row }">{{ row.dataset_name || '未命名数据集' }}</template>
              </el-table-column>
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
            <div class="pager-line">第 {{ page }} 页 · 共 {{ total }} 条</div>
            <el-pagination
              v-model:current-page="page"
              v-model:page-size="pageSize"
              :total="total"
              layout="total, sizes, prev, pager, next"
              class="pagination"
              @change="loadReports"
            />
          </template>
        </el-card>
      </el-tab-pane>
      <el-tab-pane label="问题工单" name="issues">
        <el-card>
          <div class="toolbar">
            <el-select v-model="issueStatus" placeholder="状态" clearable style="width: 140px" @change="onIssueFilter">
              <el-option label="待处理" value="open" />
              <el-option label="已忽略" value="ignored" />
              <el-option label="已复核" value="reviewed" />
              <el-option label="已修复" value="fixed" />
            </el-select>
          </div>
          <PageAsyncState
            v-if="['loading', 'error', 'forbidden', 'uncreated'].includes(issueState)"
            :state="issueState"
            :errorMessage="issuesLoadError"
          />
          <template v-else>
            <el-table :data="issues" stripe>
              <template #empty>
                <EmptyState type="default" title="暂无问题工单" description="调整筛选或从检测报告进入对应问题" />
              </template>
              <el-table-column prop="id" label="ID" width="70" />
              <el-table-column label="数据集" min-width="160" show-overflow-tooltip>
                <template #default="{ row }">{{ row.dataset_name || '未命名数据集' }}</template>
              </el-table-column>
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
            <div class="pager-line">第 {{ issuePage }} 页 · 共 {{ issueTotal }} 条</div>
            <el-pagination
              v-model:current-page="issuePage"
              v-model:page-size="issuePageSize"
              :total="issueTotal"
              layout="total, sizes, prev, pager, next"
              class="pagination"
              @change="loadIssues"
            />
          </template>
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
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { qualityApi } from '@/api'
import { useUserStore } from '@/stores/user'
import EmptyState from '@/components/EmptyState.vue'
import PageAsyncState from '@/components/PageAsyncState.vue'
import { deriveAsyncState } from '@/utils/asyncState.js'
import { readListQuery, writeListQuery } from '@/utils/listQuery.js'

const userStore = useUserStore()
const router = useRouter()
const route = useRoute()
const initialQuery = readListQuery(route.query)
const tab = ref(typeof route.query.tab === 'string' ? route.query.tab : 'reports')
const loading = ref(false)
const loadError = ref('')
const createdOnce = ref(false)
const forbidden = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(initialQuery.page)
const pageSize = ref(initialQuery.page_size)
const issues = ref([])
const issueTotal = ref(0)
const issuePage = ref(Number.parseInt(route.query.issue_page, 10) || 1)
const issuePageSize = ref(Number.parseInt(route.query.issue_page_size, 10) || 20)
const issueStatus = ref(initialQuery.status)
const issuesLoadError = ref('')
const issuesCreatedOnce = ref(false)
const issuesForbidden = ref(false)
const issuesLoading = ref(false)
const reportId = ref(route.query.report_id ? Number(route.query.report_id) : null)
const rules = ref([])

const reportState = computed(() => deriveAsyncState({
  loading: loading.value && !createdOnce.value,
  error: loadError.value,
  forbidden: forbidden.value,
  items: items.value,
  createdOnce: createdOnce.value,
}))
const issueState = computed(() => deriveAsyncState({
  loading: issuesLoading.value && !issuesCreatedOnce.value,
  error: issuesLoadError.value,
  forbidden: issuesForbidden.value,
  items: issues.value,
  createdOnce: issuesCreatedOnce.value,
}))

function listErr(e, fallback) {
  const d = e?.response?.data
  const msg = d?.message || d?.detail || e?.message
  return typeof msg === 'string' && msg ? msg : fallback
}

function summarize(report) {
  const issueMap = report?.issues || {}
  return Object.entries(issueMap).map(([k, v]) => `${k}:${v}`).join('，') || '-'
}

async function persistQuery() {
  await writeListQuery(router, {
    page: page.value,
    page_size: pageSize.value,
    q: '',
    status: issueStatus.value,
    tab: tab.value,
    issue_page: issuePage.value,
    issue_page_size: issuePageSize.value,
    report_id: reportId.value,
  })
}

async function loadReports() {
  await persistQuery()
  loading.value = true
  loadError.value = ''
  forbidden.value = false
  try {
    const res = await qualityApi.list({ page: page.value, page_size: pageSize.value })
    items.value = res.items || []
    total.value = res.total || 0
    createdOnce.value = true
  } catch (e) {
    loadError.value = listErr(e, '质量报告加载失败')
    if (e?.response?.status === 403) forbidden.value = true
  } finally {
    loading.value = false
  }
}

async function loadIssues() {
  await persistQuery()
  issuesLoading.value = true
  issuesLoadError.value = ''
  issuesForbidden.value = false
  try {
    const res = await qualityApi.issues({
      page: issuePage.value,
      page_size: issuePageSize.value,
      status: issueStatus.value || undefined,
      report_id: reportId.value || undefined,
    })
    issues.value = res.items || []
    issueTotal.value = res.total || 0
    issuesCreatedOnce.value = true
  } catch (e) {
    issuesLoadError.value = listErr(e, '问题工单加载失败')
    if (e?.response?.status === 403) issuesForbidden.value = true
  } finally {
    issuesLoading.value = false
  }
}

async function loadRules() {
  rules.value = await qualityApi.rules()
}

function onIssueFilter() {
  issuePage.value = 1
  loadIssues()
}

function openIssues(row) {
  tab.value = 'issues'
  reportId.value = row.id
  issuePage.value = 1
  loadIssues()
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
  loadIssues()
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
  persistQuery()
  if (v === 'issues' && !issuesCreatedOnce.value) loadIssues()
  if (v === 'rules' && !rules.value.length) loadRules()
})

watch(() => route.query, () => {
  const next = readListQuery(route.query)
  const nextTab = typeof route.query.tab === 'string' ? route.query.tab : 'reports'
  const nextIssuePage = Number.parseInt(route.query.issue_page, 10) || 1
  const nextIssueSize = Number.parseInt(route.query.issue_page_size, 10) || 20
  const nextReportId = route.query.report_id ? Number(route.query.report_id) : null
  if (
    next.page === page.value
    && next.page_size === pageSize.value
    && next.status === issueStatus.value
    && nextTab === tab.value
    && nextIssuePage === issuePage.value
    && nextIssueSize === issuePageSize.value
    && nextReportId === reportId.value
  ) return
  page.value = next.page
  pageSize.value = next.page_size
  issueStatus.value = next.status
  tab.value = nextTab
  issuePage.value = nextIssuePage
  issuePageSize.value = nextIssueSize
  reportId.value = nextReportId
  if (tab.value === 'reports') loadReports()
  if (tab.value === 'issues') loadIssues()
})

onMounted(() => {
  if (tab.value === 'issues') loadIssues()
  else loadReports()
})
</script>

<style scoped>
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.pagination { margin-top: 16px; justify-content: flex-end; }
.pager-line { margin-top: 12px; font-size: 13px; color: var(--text-secondary); }
</style>
