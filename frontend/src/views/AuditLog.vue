<template>
  <div class="audit-log-page">
    <div class="page-header">
      <p class="page-desc">记录登录、删除、权限变更等关键操作</p>
    </div>
    <el-card>
      <div class="toolbar">
        <el-input v-model="usernameFilter" placeholder="操作人" clearable style="width: 140px" />
        <el-button type="primary" link @click="showMoreFilters = !showMoreFilters">
          {{ showMoreFilters ? '收起筛选' : extraFilterItems.length ? `更多筛选 (${extraFilterItems.length})` : '更多筛选' }}
        </el-button>
      </div>
      <div v-show="showMoreFilters" class="toolbar toolbar-more">
        <el-select v-model="resourceFilter" placeholder="资源" clearable style="width: 120px">
          <el-option label="全部" value="" />
          <el-option label="认证" value="auth" />
          <el-option label="用户" value="user" />
          <el-option label="角色" value="role" />
          <el-option label="通知" value="notification" />
        </el-select>
        <el-select v-model="actionFilter" placeholder="操作" clearable style="width: 120px">
          <el-option label="全部" value="" />
          <el-option label="登录" value="login" />
          <el-option label="注册" value="register" />
          <el-option label="创建" value="create" />
          <el-option label="更新" value="update" />
          <el-option label="删除" value="delete" />
        </el-select>
        <el-date-picker
          v-model="createdAtRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          clearable
          style="width: 240px"
        />
      </div>
      <ActiveFilterHint
        :visible="!showMoreFilters"
        :items="extraFilterItems"
        @remove="clearExtraFilter"
        @clear="clearExtraFilters"
      />
      <el-table v-loading="loading" :data="items" stripe>
        <el-table-column prop="id" label="ID" width="72" />
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="username" label="操作人" width="100" />
        <el-table-column prop="resource" label="资源" width="100">
          <template #default="{ row }">{{ resourceLabel(row.resource) }}</template>
        </el-table-column>
        <el-table-column prop="action" label="操作" width="100">
          <template #default="{ row }">{{ actionLabel(row.action) }}</template>
        </el-table-column>
        <el-table-column prop="target_id" label="对象ID" width="88" />
        <el-table-column prop="detail" label="说明" min-width="160" show-overflow-tooltip />
        <el-table-column prop="ip" label="IP" width="120" show-overflow-tooltip />
      </el-table>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100, 200, 500]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @change="loadData"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { auditApi } from '@/api'
import ActiveFilterHint from '@/components/ActiveFilterHint.vue'

const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const resourceFilter = ref('')
const actionFilter = ref('')
const usernameFilter = ref('')
const createdAtRange = ref(null)
const showMoreFilters = ref(false)
const listReady = ref(false)
let searchTimer = null

const extraFilterItems = computed(() => {
  const items = []
  if (resourceFilter.value) items.push({ key: 'resource', label: '资源', text: resourceLabel(resourceFilter.value) })
  if (actionFilter.value) items.push({ key: 'action', label: '操作', text: actionLabel(actionFilter.value) })
  if (createdAtRange.value?.length === 2) {
    items.push({ key: 'createdAt', label: '时间', text: `${createdAtRange.value[0]} 至 ${createdAtRange.value[1]}` })
  }
  return items
})

function clearExtraFilter(key) {
  if (key === 'resource') resourceFilter.value = ''
  else if (key === 'action') actionFilter.value = ''
  else if (key === 'createdAt') createdAtRange.value = null
}

function clearExtraFilters() {
  resourceFilter.value = ''
  actionFilter.value = ''
  createdAtRange.value = null
}

const resourceLabels = {
  auth: '认证',
  dataset: '数据集',
  task: '任务',
  model: '微调模型',
  base_model: '基础模型',
  user: '用户',
  role: '角色',
  notification: '通知'
}

const actionLabels = {
  login: '登录',
  register: '注册',
  create: '创建',
  update: '更新',
  delete: '删除',
  batch_delete: '批量删除',
  deploy: '部署',
  undeploy: '停止部署',
  stop: '停止',
  retry: '重试'
}

function resourceLabel(r) {
  return resourceLabels[r] || r
}

function actionLabel(a) {
  return actionLabels[a] || a
}

function formatDate(v) {
  if (!v) return '-'
  const d = new Date(v)
  return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

async function loadData() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (resourceFilter.value) params.resource = resourceFilter.value
    if (actionFilter.value) params.action = actionFilter.value
    if (usernameFilter.value) params.username = usernameFilter.value
    if (createdAtRange.value && createdAtRange.value.length === 2) {
      params.created_at_start = createdAtRange.value[0]
      params.created_at_end = createdAtRange.value[1]
    }
    const res = await auditApi.list(params)
    items.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadData()
  listReady.value = true
})

watch(
  () => [resourceFilter.value, actionFilter.value, createdAtRange.value],
  () => {
    if (!listReady.value) return
    page.value = 1
    loadData()
  }
)
watch(usernameFilter, () => {
  if (!listReady.value) return
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    loadData()
  }, 300)
})
</script>

<style scoped>
.audit-log-page .page-header { margin-bottom: 16px; }
.audit-log-page .page-desc { margin: 4px 0 0; font-size: 13px; color: var(--text-secondary); }
.audit-log-page .pagination { margin-top: 16px; justify-content: flex-end; }
</style>
