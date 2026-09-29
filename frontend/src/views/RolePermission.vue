<template>
  <div class="role-permission-page">
    <div class="page-header">
      <p class="page-desc">配置角色权限、数据范围，控制页面/按钮显隐与数据可见性</p>
    </div>

    <PageAsyncState
      v-if="['loading', 'error', 'forbidden', 'uncreated'].includes(pageState)"
      :state="pageState"
      :errorMessage="loadError"
    />
    <el-row v-else :gutter="24">
      <!-- 角色列表 -->
      <el-col :span="6">
        <el-card class="role-card" shadow="hover">
          <template #header>
            <span>角色</span>
          </template>
          <div class="role-list">
            <div
              v-for="ro in roles"
              :key="ro.id"
              class="role-item"
              :class="{ active: selectedRole?.id === ro.id }"
              @click="selectRole(ro)"
            >
              <el-tag :type="roleTagType(ro.code)" size="small">{{ roleName(ro) }}</el-tag>
              <el-tag v-if="ro.code === 'admin'" type="info" size="small" effect="plain">不可编辑</el-tag>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 权限配置 -->
      <el-col :span="18">
        <el-card v-if="selectedRole" class="config-card" shadow="hover">
          <template #header>
            <div class="config-header">
              <span>{{ roleName(selectedRole) }} 权限配置</span>
              <el-button type="primary" :loading="saving" :disabled="selectedRole.code === 'admin'" @click="save">
                保存
              </el-button>
            </div>
          </template>

          <!-- 数据范围 -->
          <div class="config-section">
            <h4>数据可见性</h4>
            <el-radio-group v-model="form.data_scope" :disabled="selectedRole.code === 'admin'">
              <el-radio value="all">
                全部数据 - 可查看/操作平台内所有数据
              </el-radio>
              <el-radio value="own">
                仅自己的数据 - 仅可查看/操作自己创建或上传的数据
              </el-radio>
            </el-radio-group>
          </div>

          <!-- 权限矩阵 -->
          <div class="config-section">
            <h4>功能权限（控制页面、按钮显隐）</h4>
            <el-table :data="permissionGroups" border size="small">
              <el-table-column prop="resourceName" label="资源/模块" width="140">
                <template #default="{ row }">{{ resourceLabel(row) }}</template>
              </el-table-column>
              <el-table-column label="权限项">
                <template #default="{ row }">
                  <el-checkbox-group v-model="form.permission_codes" :disabled="selectedRole.code === 'admin'">
                    <el-checkbox
                      v-for="act in row.actions"
                      :key="act.code"
                      :value="act.code"
                      style="margin-right: 16px; margin-bottom: 4px"
                    >
                      {{ actionLabel(act) }}
                    </el-checkbox>
                  </el-checkbox-group>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 快捷操作 -->
          <div class="config-section">
            <h4>快捷操作</h4>
            <el-space wrap>
              <el-button size="small" @click="selectAll">全选</el-button>
              <el-button size="small" @click="selectNone">清空</el-button>
              <el-button size="small" @click="selectReadOnly">仅读权限</el-button>
            </el-space>
          </div>
        </el-card>

        <EmptyState v-else type="role" :show-action="false" />
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { rolesApi } from '@/api'
import EmptyState from '@/components/EmptyState.vue'
import PageAsyncState from '@/components/PageAsyncState.vue'
import { deriveAsyncState } from '@/utils/asyncState.js'

const roles = ref([])
const permissionGroups = ref([])
const selectedRole = ref(null)
const saving = ref(false)
const loading = ref(false)
const loadError = ref('')
const createdOnce = ref(false)

const form = reactive({
  data_scope: 'all',
  permission_codes: []
})

const pageState = computed(() => deriveAsyncState({
  loading: loading.value && !createdOnce.value,
  error: loadError.value,
  forbidden: false,
  items: roles.value,
  createdOnce: createdOnce.value,
}))

function loadErr(e, fallback) {
  const d = e?.response?.data
  const msg = d?.message || d?.detail || e?.message
  return typeof msg === 'string' && msg ? msg : fallback
}

function roleTagType(code) {
  const map = { admin: 'danger', researcher: 'success', viewer: 'info' }
  return map[code] || 'info'
}

const ROLE_CODE_NAMES = {
  admin: '管理员',
  researcher: '评测人员',
  viewer: '访客'
}

const ACTION_NAMES = {
  list: '列表',
  view: '详情',
  view_mine: '我的',
  create: '创建',
  edit: '编辑',
  delete: '删除',
  deploy: '部署',
  undeploy: '停止部署',
  inference: '推理测试',
  download: '下载',
  stop: '停止',
  evaluate: '模型评估',
  comparative_eval: '对比评估',
  eval_review: '评估人工评审'
}

function roleName(ro) {
  if (ro?.name && /[\u4e00-\u9fff]/.test(ro.name)) return ro.name
  return ROLE_CODE_NAMES[ro?.code] || ro?.name || ro?.code
}

const RESOURCE_NAMES = {
  dashboard: '仪表盘',
  dataset: '数据集',
  base_model: '基础模型',
  task: '任务',
  model: '微调模型',
  user: '用户管理',
  notification: '通知',
  role: '权限管理',
  system_monitor: '系统监控',
  audit: '操作审计',
  experiment: '实验分组',
  task_template: '任务模板',
  capability: '能力分类',
  scenario: '业务场景',
  schedule: '模型调度',
  compute_node: '算力节点',
  prompt_template: '提示词模板'
}

function resourceLabel(row) {
  const name = row?.resourceName || ''
  if (name && /[\u4e00-\u9fff]/.test(name)) return name
  return RESOURCE_NAMES[row?.resource] || name || row?.resource
}

function actionLabel(act) {
  const name = act?.name || ''
  if (name && /[\u4e00-\u9fff]/.test(name)) return name
  return ACTION_NAMES[act?.action] || name || act?.code
}

async function loadRoles() {
  try {
    roles.value = await rolesApi.list()
  } catch (e) {
    loadError.value = loadErr(e, '角色列表加载失败')
  }
}

async function loadPermissions() {
  try {
    permissionGroups.value = await rolesApi.listPermissions()
  } catch (e) {
    if (!loadError.value) loadError.value = loadErr(e, '权限目录加载失败')
  }
}

async function selectRole(ro) {
  if (ro.code === 'admin') {
    selectedRole.value = ro
    form.data_scope = 'all'
    const allCodes = permissionGroups.value.flatMap((g) => g.actions.map((a) => a.code))
    form.permission_codes = [...allCodes]
    return
  }
  try {
    const detail = await rolesApi.get(ro.id)
    selectedRole.value = ro
    form.data_scope = detail.data_scope || 'all'
    form.permission_codes = [...(detail.permission_codes || [])]
  } catch (_) {
    ElMessage.error('加载角色失败')
  }
}

function selectAll() {
  if (selectedRole.value?.code === 'admin') return
  const allCodes = permissionGroups.value.flatMap((g) => g.actions.map((a) => a.code))
  form.permission_codes = [...allCodes]
}

function selectNone() {
  if (selectedRole.value?.code === 'admin') return
  form.permission_codes = []
}

function selectReadOnly() {
  if (selectedRole.value?.code === 'admin') return
  const readOnly = ['list', 'view', 'view_mine']
  form.permission_codes = permissionGroups.value.flatMap((g) =>
    g.actions.filter((a) => readOnly.includes(a.action)).map((a) => a.code)
  )
}

async function save() {
  if (!selectedRole.value || selectedRole.value.code === 'admin') return
  saving.value = true
  try {
    await rolesApi.update(selectedRole.value.id, {
      data_scope: form.data_scope,
      permission_codes: form.permission_codes
    })
    ElMessage.success('保存成功')
    loadRoles()
  } catch (e) {
    ElMessage.error(loadErr(e, '保存失败'))
  }
  finally {
    saving.value = false
  }
}

onMounted(async () => {
  loading.value = true
  loadError.value = ''
  try {
    await loadPermissions()
    await loadRoles()
    createdOnce.value = !loadError.value
    if (roles.value.length && !selectedRole.value) {
      selectRole(roles.value.find((r) => r.code === 'researcher') || roles.value[0])
    }
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.role-permission-page {
  max-width: 1200px;
}
.page-header {
  margin-bottom: 24px;
}
.page-desc {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}
.role-card,
.config-card {
  min-height: 400px;
}
.role-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.role-item {
  padding: 12px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 0.2s;
}
.role-item:hover {
  background: var(--border-light);
}
.role-item.active {
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
  border: 1px solid var(--color-primary);
}
.role-code {
  font-size: 12px;
  color: var(--text-secondary);
}
.config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.config-section {
  margin-bottom: 24px;
}
.config-section:last-child {
  margin-bottom: 0;
}
.config-section h4 {
  margin: 0 0 12px;
  font-size: 14px;
  color: var(--text-secondary);
}
</style>
