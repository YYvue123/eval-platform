<template>
  <div class="notification-manage">
    <div class="page-header">
      <div>
        <h2 class="page-title">通知管理</h2>
      </div>
      <el-button v-if="userStore.hasPermission('notification:create')" type="primary" @click="showCreate = true">
        <el-icon><Plus /></el-icon>
        发送通知
      </el-button>
    </div>
    <el-card>
      <div class="toolbar">
        <el-input
          v-model="search"
          placeholder="搜索标题或内容"
          clearable
          style="width: 220px"
        />
        <el-select v-model="typeFilter" placeholder="类型筛选" clearable style="width: 120px">
          <el-option label="全部类型" value="" />
          <el-option label="提示" value="info" />
          <el-option label="成功" value="success" />
          <el-option label="警告" value="warning" />
          <el-option label="错误" value="error" />
        </el-select>
        <el-button type="primary" link @click="showMoreFilters = !showMoreFilters">
          {{ showMoreFilters ? '收起筛选' : extraFilterItems.length ? `更多筛选 (${extraFilterItems.length})` : '更多筛选' }}
        </el-button>
      </div>
      <div v-show="showMoreFilters" class="toolbar toolbar-more">
        <el-select v-model="targetFilter" placeholder="目标筛选" clearable style="width: 130px">
          <el-option label="全部" value="" />
          <el-option label="广播（全体用户）" value="all" />
          <el-option label="指定用户" value="user" />
        </el-select>
        <el-date-picker v-model="createdAtRange" type="daterange" range-separator="至" start-placeholder="创建时间起" end-placeholder="创建时间止" value-format="YYYY-MM-DD" clearable style="width: 240px" />
        <el-select v-model="sortBy" placeholder="排序" style="width: 130px">
          <el-option label="发送时间" value="created_at" />
          <el-option label="标题" value="title" />
          <el-option label="类型" value="type" />
          <el-option label="ID" value="id" />
        </el-select>
        <el-select v-model="sortOrder" placeholder="方向" style="width: 90px">
          <el-option label="倒序" value="desc" />
          <el-option label="正序" value="asc" />
        </el-select>
      </div>
      <ActiveFilterHint
        :visible="!showMoreFilters"
        :items="extraFilterItems"
        @remove="clearExtraFilter"
        @clear="clearExtraFilters"
      />
      <PageAsyncState
        v-if="['loading', 'error', 'forbidden', 'uncreated'].includes(listState)"
        :state="listState"
        :errorMessage="loadError"
      />
      <template v-else>
      <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange">
        <template #empty>
          <EmptyState type="notification" action-text="发送通知" :show-action="userStore.hasPermission('notification:create')" @action="showCreate = true" />
        </template>
        <el-table-column prop="id" label="ID" width="80" sortable="custom" />
        <el-table-column prop="title" label="标题" min-width="160" sortable="custom" />
        <el-table-column prop="message" label="内容" min-width="200" show-overflow-tooltip />
        <el-table-column prop="type" label="类型" width="100" sortable="custom">
          <template #default="{ row }">
            <el-tag :type="row.type === 'error' ? 'danger' : row.type" size="small">{{ typeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="user_id" label="目标" width="120">
          <template #default="{ row }">{{ row.user_id == null ? '全体用户' : `用户 #${row.user_id}` }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="发送时间" width="180" sortable="custom">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <div class="op-btns">
              <el-popconfirm
                v-if="userStore.hasPermission('notification:delete')"
                title="确定删除该通知？"
                confirm-button-text="删除"
                cancel-button-text="取消"
                @confirm="handleDelete(row.id)"
              >
                <template #reference>
                  <el-button link type="danger" size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50, 100, 200, 500]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @change="loadData"
      />
      </template>
    </el-card>

    <el-dialog v-model="showCreate" title="发送通知" width="480px" @close="resetCreate">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="通知标题" />
        </el-form-item>
        <el-form-item label="内容" prop="message">
          <el-input v-model="form.message" type="textarea" rows="3" placeholder="通知内容（可选）" />
        </el-form-item>
        <el-form-item label="类型" prop="type">
          <el-select v-model="form.type" placeholder="类型" style="width: 100%">
            <el-option label="提示" value="info" />
            <el-option label="成功" value="success" />
            <el-option label="警告" value="warning" />
            <el-option label="错误" value="error" />
          </el-select>
        </el-form-item>
        <el-form-item label="发送给">
          <el-select v-model="form.user_id" placeholder="全体用户" clearable style="width: 100%">
            <el-option label="全体用户" :value="null" />
            <el-option v-for="u in users" :key="u.id" :label="u.username" :value="u.id" />
          </el-select>
          <div v-if="usersLoadError" class="hint">{{ usersLoadError }}</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCreate">发送</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import EmptyState from '@/components/EmptyState.vue'
import PageAsyncState from '@/components/PageAsyncState.vue'
import ActiveFilterHint from '@/components/ActiveFilterHint.vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { notificationsApi, usersApi } from '@/api'
import { deriveAsyncState } from '@/utils/asyncState.js'

const userStore = useUserStore()

const loading = ref(false)
const loadError = ref('')
const createdOnce = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const search = ref('')
const typeFilter = ref('')
const targetFilter = ref('')
const createdAtRange = ref(null)
const sortBy = ref('created_at')
const sortOrder = ref('desc')
const showMoreFilters = ref(false)
const listReady = ref(false)
let searchTimer = null

const listState = computed(() => deriveAsyncState({
  loading: loading.value && !createdOnce.value,
  error: loadError.value,
  forbidden: false,
  items: items.value,
  createdOnce: createdOnce.value,
}))

function loadErr(e, fallback) {
  const d = e?.response?.data
  const msg = d?.message || d?.detail || e?.message
  return typeof msg === 'string' && msg ? msg : fallback
}

const NOTICE_SORT_LABELS = { created_at: '发送时间', title: '标题', type: '类型', id: 'ID' }

const extraFilterItems = computed(() => {
  const items = []
  if (targetFilter.value) {
    items.push({ key: 'target', label: '目标', text: targetFilter.value === 'all' ? '广播（全体用户）' : '指定用户' })
  }
  if (createdAtRange.value?.length === 2) {
    items.push({ key: 'createdAt', label: '创建时间', text: `${createdAtRange.value[0]} 至 ${createdAtRange.value[1]}` })
  }
  if (sortBy.value !== 'created_at' || sortOrder.value !== 'desc') {
    items.push({
      key: 'sort',
      label: '排序',
      text: `${NOTICE_SORT_LABELS[sortBy.value] || sortBy.value} ${sortOrder.value === 'asc' ? '正序' : '倒序'}`
    })
  }
  return items
})

function clearExtraFilter(key) {
  if (key === 'target') targetFilter.value = ''
  else if (key === 'createdAt') createdAtRange.value = null
  else if (key === 'sort') {
    sortBy.value = 'created_at'
    sortOrder.value = 'desc'
  }
}

function clearExtraFilters() {
  targetFilter.value = ''
  createdAtRange.value = null
  sortBy.value = 'created_at'
  sortOrder.value = 'desc'
}

const showCreate = ref(false)
const formRef = ref()
const form = reactive({ title: '', message: '', type: 'info', user_id: null })
const rules = { title: [{ required: true, message: '请输入标题', trigger: 'blur' }] }
const submitting = ref(false)
const users = ref([])
const usersLoadError = ref('')

function typeLabel(type) {
  const map = { info: '提示', success: '成功', warning: '警告', error: '错误' }
  return map[type] || type
}

function formatDate(s) {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN')
}

async function loadData() {
  loading.value = true
  loadError.value = ''
  try {
    const params = { page: page.value, page_size: pageSize.value, search: search.value, type: typeFilter.value, target: targetFilter.value, sort_by: sortBy.value, sort_order: sortOrder.value }
    if (createdAtRange.value && createdAtRange.value.length === 2) {
      params.created_at_start = createdAtRange.value[0]
      params.created_at_end = createdAtRange.value[1]
    }
    const res = await notificationsApi.list(params)
    items.value = res.items || []
    total.value = res.total || 0
    createdOnce.value = true
  } catch (e) {
    loadError.value = loadErr(e, '通知列表加载失败')
  } finally {
    loading.value = false
  }
}

function handleQuery() {
  page.value = 1
  loadData()
}

function onSortChange({ prop, order }) {
  if (!prop) return
  const map = { id: 'id', title: 'title', type: 'type', created_at: 'created_at' }
  sortBy.value = map[prop] || 'created_at'
  sortOrder.value = order === 'ascending' ? 'asc' : 'desc'
  page.value = 1
  loadData()
}

async function loadUsers() {
  usersLoadError.value = ''
  try {
    const res = await usersApi.list({ page: 1, page_size: 100 })
    users.value = res.items || []
  } catch (err) {
    users.value = []
    const data = err?.response?.data
    const msg = data?.message ?? data?.detail ?? err?.message
    usersLoadError.value = typeof msg === 'string' && msg ? msg : '用户列表加载失败'
  }
}

function resetCreate() {
  form.title = ''
  form.message = ''
  form.type = 'info'
  form.user_id = null
}

async function submitCreate() {
  await formRef.value.validate()
  submitting.value = true
  try {
    await notificationsApi.create(form)
    ElMessage.success('发送成功')
    showCreate.value = false
    loadData()
  } finally {
    submitting.value = false
  }
}

async function handleDelete(id) {
  try {
    await notificationsApi.delete(id)
    ElMessage.success('删除成功')
    loadData()
  } catch (_) {}
}

onMounted(async () => {
  await loadData()
  loadUsers()
  listReady.value = true
})

watch(
  () => [typeFilter.value, targetFilter.value, createdAtRange.value, sortBy.value, sortOrder.value],
  () => {
    if (!listReady.value) return
    page.value = 1
    loadData()
  }
)
watch(search, () => {
  if (!listReady.value) return
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    loadData()
  }, 300)
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.toolbar { margin-bottom: 12px; display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.toolbar-more { margin-bottom: 16px; }
.pagination { margin-top: 16px; justify-content: flex-end; }
.hint { color: var(--text-secondary); font-size: 13px; margin-top: 6px; }
</style>
