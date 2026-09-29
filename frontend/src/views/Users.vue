<template>
  <div class="users-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">用户管理</h2>
      </div>
      <el-button v-if="userStore.hasPermission('user:create')" type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>
        新增用户
      </el-button>
    </div>
    <el-card>
      <div v-if="userStore.hasPermission('user:list')" class="toolbar">
        <el-input
          v-model="search"
          placeholder="搜索用户名/手机/邮箱"
          clearable
          style="width: 220px"
        />
        <el-select v-model="roleFilter" placeholder="角色筛选" clearable style="width: 120px">
          <el-option label="全部角色" value="" />
          <el-option label="管理员" value="admin" />
          <el-option label="评测人员" value="researcher" />
          <el-option label="访客" value="viewer" />
        </el-select>
        <el-button type="primary" link @click="showMoreFilters = !showMoreFilters">
          {{ showMoreFilters ? '收起筛选' : extraFilterItems.length ? `更多筛选 (${extraFilterItems.length})` : '更多筛选' }}
        </el-button>
      </div>
      <div v-if="userStore.hasPermission('user:list')" v-show="showMoreFilters" class="toolbar toolbar-more">
        <el-select v-model="creatorFilter" placeholder="创建人" clearable style="width: 120px">
          <el-option label="全部" :value="null" />
          <el-option v-for="u in creatorOptions" :key="u.id" :label="u.username" :value="u.id" />
        </el-select>
        <span v-if="creatorOptionsError" class="hint">{{ creatorOptionsError }}</span>
        <el-date-picker v-model="createdAtRange" type="daterange" range-separator="至" start-placeholder="创建时间起" end-placeholder="创建时间止" value-format="YYYY-MM-DD" clearable style="width: 240px" />
        <el-select v-model="sortBy" placeholder="排序字段" style="width: 130px">
          <el-option label="创建时间" value="created_at" />
          <el-option label="用户名" value="username" />
          <el-option label="ID" value="id" />
          <el-option label="更新时间" value="updated_at" />
        </el-select>
        <el-select v-model="sortOrder" placeholder="排序方向" style="width: 110px">
          <el-option label="倒序" value="desc" />
          <el-option label="正序" value="asc" />
        </el-select>
      </div>
      <ActiveFilterHint
        v-if="userStore.hasPermission('user:list')"
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
          <EmptyState type="user" action-text="新增用户" :show-action="userStore.hasPermission('user:create')" @action="openCreate" />
        </template>
        <el-table-column prop="id" label="ID" width="80" sortable="custom" />
        <el-table-column prop="username" label="用户名" width="140" sortable="custom" />
        <el-table-column prop="phone" label="手机号" width="140" />
        <el-table-column prop="email" label="邮箱" min-width="180" />
        <el-table-column v-if="userStore.hasPermission('user:list')" prop="role" label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : row.role === 'researcher' ? 'success' : 'info'">
              {{ row.role === 'admin' ? '管理员' : row.role === 'researcher' ? '评测人员' : '访客' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">{{ row.status === 'disabled' ? '已禁用' : '启用' }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" sortable="custom">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="created_by_username" label="创建人" width="100">
          <template #default="{ row }">{{ row.created_by_username || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <div class="op-btns">
              <el-button v-if="userStore.hasPermission('user:edit')" link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
              <el-button
                v-if="userStore.hasPermission('user:edit') && row.id !== currentUserId"
                link
                size="small"
                :type="row.status === 'disabled' ? 'success' : 'warning'"
                @click="toggleStatus(row)"
              >{{ row.status === 'disabled' ? '启用' : '禁用' }}</el-button>
              <el-button v-if="userStore.hasPermission('user:delete') && row.role !== 'admin' && row.id !== currentUserId" link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager-line">第 {{ page }} 页 · 共 {{ total }} 条</div>
      <el-pagination
        v-if="userStore.hasPermission('user:list')"
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

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="showForm" :title="formMode === 'create' ? '新增用户' : '编辑用户'" width="480px" @close="resetForm">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" :disabled="formMode === 'edit'" />
        </el-form-item>
        <el-form-item v-if="formMode === 'create'" label="密码" prop="password">
          <el-input v-model="form.password" type="password" placeholder="字母与数字组合，大于6位" show-password />
          <div v-if="form.password" class="password-strength">
            <span class="strength-label">强度：</span>
            <el-progress :percentage="passwordStrength.level * 25" :stroke-width="6" :color="userStrengthColor" :show-text="false" />
            <span :class="['strength-text', 'strength-' + passwordStrength.type]">{{ passwordStrength.label }}</span>
          </div>
        </el-form-item>
        <el-form-item v-else label="新密码">
          <el-input v-model="form.password" type="password" placeholder="不修改请留空；修改时需字母与数字组合、大于6位" show-password />
          <div v-if="form.password" class="password-strength">
            <span class="strength-label">强度：</span>
            <el-progress :percentage="passwordStrength.level * 25" :stroke-width="6" :color="userStrengthColor" :show-text="false" />
            <span :class="['strength-text', 'strength-' + passwordStrength.type]">{{ passwordStrength.label }}</span>
          </div>
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="form.phone" placeholder="请输入手机号" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item v-if="userStore.hasPermission('user:create') && formMode === 'create'" label="角色" prop="role">
          <el-select v-model="form.role" placeholder="选择角色" style="width: 100%">
            <el-option label="访客" value="viewer" />
            <el-option label="评测人员" value="researcher" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="userStore.hasPermission('user:edit') && formMode === 'edit'" label="角色" prop="role">
          <el-select v-model="form.role" placeholder="选择角色" style="width: 100%">
            <el-option label="访客" value="viewer" />
            <el-option label="评测人员" value="researcher" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showDelete" title="确认删除" width="400px">
      <p>确定要删除用户「{{ deleteTarget?.username }}」吗？</p>
      <template #footer>
        <el-button @click="showDelete = false">取消</el-button>
        <el-button type="danger" :loading="deleting" @click="confirmDelete">删除</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { usersApi } from '@/api'
import EmptyState from '@/components/EmptyState.vue'
import ActiveFilterHint from '@/components/ActiveFilterHint.vue'
import PageAsyncState from '@/components/PageAsyncState.vue'
import { getPasswordStrength, validatePassword } from '@/utils/password'
import { deriveAsyncState } from '@/utils/asyncState.js'
import { readListQuery, writeListQuery } from '@/utils/listQuery.js'

const userStore = useUserStore()
const router = useRouter()
const route = useRoute()
const initialQuery = readListQuery(route.query)
const isAdmin = computed(() => userStore.isAdmin())
const currentUserId = ref(null)

const loading = ref(false)
const loadError = ref('')
const createdOnce = ref(false)
const forbidden = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(initialQuery.page)
const pageSize = ref(initialQuery.page_size)
const search = ref(initialQuery.q)
const roleFilter = ref(typeof route.query.role === 'string' ? route.query.role : '')
const creatorFilter = ref(route.query.created_by ? Number(route.query.created_by) : null)
const creatorOptions = ref([])
const creatorOptionsError = ref('')
const createdAtRange = ref(
  route.query.created_at_start && route.query.created_at_end
    ? [String(route.query.created_at_start), String(route.query.created_at_end)]
    : null
)
const sortBy = ref(typeof route.query.sort_by === 'string' ? route.query.sort_by : 'created_at')
const sortOrder = ref(typeof route.query.sort_order === 'string' ? route.query.sort_order : 'desc')
const showMoreFilters = ref(false)
const listReady = ref(false)
let searchTimer = null
let skipFilterWatch = false

const listState = computed(() => deriveAsyncState({
  loading: loading.value && !createdOnce.value,
  error: loadError.value,
  forbidden: forbidden.value,
  items: items.value,
  createdOnce: createdOnce.value,
}))

function listErr(e, fallback) {
  const d = e?.response?.data
  const msg = d?.message || d?.detail || e?.message
  return typeof msg === 'string' && msg ? msg : fallback
}

const USER_SORT_LABELS = { created_at: '创建时间', username: '用户名', id: 'ID', updated_at: '更新时间' }

const extraFilterItems = computed(() => {
  const items = []
  if (creatorFilter.value != null) {
    const user = creatorOptions.value.find((u) => u.id === creatorFilter.value)
    items.push({ key: 'creator', label: '创建人', text: user?.username || `#${creatorFilter.value}` })
  }
  if (createdAtRange.value?.length === 2) {
    items.push({ key: 'createdAt', label: '创建时间', text: `${createdAtRange.value[0]} 至 ${createdAtRange.value[1]}` })
  }
  if (sortBy.value !== 'created_at' || sortOrder.value !== 'desc') {
    items.push({
      key: 'sort',
      label: '排序',
      text: `${USER_SORT_LABELS[sortBy.value] || sortBy.value} ${sortOrder.value === 'asc' ? '正序' : '倒序'}`
    })
  }
  return items
})

function clearExtraFilter(key) {
  if (key === 'creator') creatorFilter.value = null
  else if (key === 'createdAt') createdAtRange.value = null
  else if (key === 'sort') {
    sortBy.value = 'created_at'
    sortOrder.value = 'desc'
  }
}

function clearExtraFilters() {
  creatorFilter.value = null
  createdAtRange.value = null
  sortBy.value = 'created_at'
  sortOrder.value = 'desc'
}

const showForm = ref(false)
const formRef = ref()
const formMode = ref('create')
const form = reactive({ username: '', password: '', phone: '', email: '', role: 'viewer' })
const passwordStrength = computed(() => getPasswordStrength(form.password))
const userStrengthColor = computed(() => {
  const t = passwordStrength.value.type
  return t === 'danger' ? '#f56c6c' : t === 'warning' ? '#e6a23c' : '#67c23a'
})
const formRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    {
      validator: (rule, value, cb) => {
        const r = validatePassword(value)
        if (!r.valid) cb(new Error(r.message))
        else cb()
      },
      trigger: 'blur'
    }
  ]
}
const editId = ref(null)
const submitting = ref(false)

const showDelete = ref(false)
const deleteTarget = ref(null)
const deleting = ref(false)

function formatDate(s) {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN')
}

function handleQuery() {
  page.value = 1
  loadData()
}

function onSortChange({ prop, order }) {
  if (!prop) return
  sortBy.value = prop === 'created_at' ? 'created_at' : prop === 'username' ? 'username' : prop === 'id' ? 'id' : 'created_at'
  sortOrder.value = order === 'ascending' ? 'asc' : 'desc'
  page.value = 1
  loadData()
}

async function persistQuery() {
  await writeListQuery(router, {
    page: page.value,
    page_size: pageSize.value,
    q: search.value,
    status: '',
    role: roleFilter.value,
    created_by: creatorFilter.value,
    created_at_start: createdAtRange.value?.[0],
    created_at_end: createdAtRange.value?.[1],
    sort_by: sortBy.value !== 'created_at' ? sortBy.value : '',
    sort_order: sortOrder.value !== 'desc' ? sortOrder.value : '',
  })
}

async function loadData() {
  await persistQuery()
  loading.value = true
  loadError.value = ''
  forbidden.value = false
  try {
    if (!currentUserId.value) {
      const me = await usersApi.getMe().catch(() => ({}))
      currentUserId.value = me?.id
    }
    const params = { page: page.value, page_size: pageSize.value, search: search.value, role: roleFilter.value, sort_by: sortBy.value, sort_order: sortOrder.value }
    if (creatorFilter.value != null) params.created_by = creatorFilter.value
    if (createdAtRange.value && createdAtRange.value.length === 2) {
      params.created_at_start = createdAtRange.value[0]
      params.created_at_end = createdAtRange.value[1]
    }
    const res = await usersApi.list(params)
    items.value = res.items || []
    total.value = res.total || 0
    createdOnce.value = true
  } catch (e) {
    loadError.value = listErr(e, '用户列表加载失败')
    if (e?.response?.status === 403) forbidden.value = true
  } finally {
    loading.value = false
  }
}

function openCreate() {
  formMode.value = 'create'
  resetForm()
  showForm.value = true
}

function openEdit(row) {
  formMode.value = 'edit'
  editId.value = row.id
  form.username = row.username
  form.password = ''
  form.phone = row.phone || ''
  form.email = row.email || ''
  form.role = row.role || 'viewer'
  formRules.password = []
  showForm.value = true
}

function resetForm() {
  formMode.value = 'create'
  editId.value = null
  form.username = ''
  form.password = ''
  form.phone = ''
  form.email = ''
  form.role = 'viewer'
  formRules.password = [
    { required: true, message: '请输入密码', trigger: 'blur' },
    {
      validator: (rule, value, cb) => {
        const r = validatePassword(value)
        if (!r.valid) cb(new Error(r.message))
        else cb()
      },
      trigger: 'blur'
    }
  ]
}

async function submitForm() {
  if (formMode.value === 'create') {
    await formRef.value.validate()
    const r = validatePassword(form.password)
    if (!r.valid) {
      ElMessage.warning(r.message)
      return
    }
  } else if (form.password) {
    const r = validatePassword(form.password)
    if (!r.valid) {
      ElMessage.warning(r.message)
      return
    }
  }
  submitting.value = true
  try {
    if (formMode.value === 'create') {
      await usersApi.create({
        username: form.username,
        password: form.password,
        phone: form.phone,
        email: form.email,
        role: form.role
      })
      ElMessage.success('新增成功')
    } else {
      const data = { phone: form.phone, email: form.email }
      if (isAdmin.value) data.role = form.role
      if (form.password) data.password = form.password
      await usersApi.update(editId.value, data)
      ElMessage.success('更新成功')
    }
    showForm.value = false
    loadData()
  } finally {
    submitting.value = false
  }
}

function handleDelete(row) {
  deleteTarget.value = row
  showDelete.value = true
}

async function toggleStatus(row) {
  const next = row.status === 'disabled' ? 'active' : 'disabled'
  if (next === 'disabled') {
    await ElMessageBox.confirm(`确定禁用用户「${row.username}」？禁用后该账号将无法登录。`, '确认禁用')
    await usersApi.update(row.id, { status: 'disabled' })
  } else {
    await usersApi.update(row.id, { status: 'active' })
  }
  ElMessage.success(next === 'disabled' ? '已禁用' : '已启用')
  loadData()
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await usersApi.delete(deleteTarget.value.id)
    ElMessage.success('删除成功')
    showDelete.value = false
    loadData()
  } finally {
    deleting.value = false
  }
}

onMounted(async () => {
  if (userStore.hasPermission('user:list')) {
    creatorOptionsError.value = ''
    try {
      creatorOptions.value = await usersApi.listOptions() || []
    } catch (e) {
      creatorOptions.value = []
      creatorOptionsError.value = listErr(e, '创建人列表加载失败')
    }
  }
  await loadData()
  listReady.value = true
})

watch(
  () => [roleFilter.value, creatorFilter.value, createdAtRange.value, sortBy.value, sortOrder.value],
  () => {
    if (!listReady.value || skipFilterWatch) return
    page.value = 1
    loadData()
  }
)
watch(search, () => {
  if (!listReady.value || skipFilterWatch) return
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    loadData()
  }, 300)
})
watch(() => route.query, () => {
  const next = readListQuery(route.query)
  const nextRole = typeof route.query.role === 'string' ? route.query.role : ''
  const nextCreator = route.query.created_by ? Number(route.query.created_by) : null
  const nextRange = route.query.created_at_start && route.query.created_at_end
    ? [String(route.query.created_at_start), String(route.query.created_at_end)]
    : null
  const nextSortBy = typeof route.query.sort_by === 'string' ? route.query.sort_by : 'created_at'
  const nextSortOrder = typeof route.query.sort_order === 'string' ? route.query.sort_order : 'desc'
  const sameRange = (nextRange?.[0] || '') === (createdAtRange.value?.[0] || '')
    && (nextRange?.[1] || '') === (createdAtRange.value?.[1] || '')
  if (
    next.page === page.value
    && next.page_size === pageSize.value
    && next.q === search.value
    && nextRole === roleFilter.value
    && nextCreator === creatorFilter.value
    && sameRange
    && nextSortBy === sortBy.value
    && nextSortOrder === sortOrder.value
  ) return
  skipFilterWatch = true
  page.value = next.page
  pageSize.value = next.page_size
  search.value = next.q
  roleFilter.value = nextRole
  creatorFilter.value = nextCreator
  createdAtRange.value = nextRange
  sortBy.value = nextSortBy
  sortOrder.value = nextSortOrder
  queueMicrotask(() => { skipFilterWatch = false })
  loadData()
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
.pager-line { margin-top: 12px; font-size: 13px; color: var(--text-secondary); }
.hint { color: var(--text-secondary); font-size: 13px; }
.password-strength { display: flex; align-items: center; gap: 8px; margin-top: 6px; font-size: 12px; }
.password-strength .strength-label { color: var(--text-secondary); }
.password-strength .el-progress { flex: 1; max-width: 120px; }
.password-strength .strength-text { min-width: 28px; }
.password-strength .strength-danger { color: var(--el-color-danger); }
.password-strength .strength-warning { color: var(--el-color-warning); }
.password-strength .strength-success { color: var(--el-color-success); }
</style>
