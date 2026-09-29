<template>
  <div class="dashboard-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">工作台</h2>
        <p class="page-desc">待办审批、进行中任务、异常与最近结果；按权限显示快捷入口。</p>
      </div>
    </div>

    <el-alert
      v-if="route.query.denied"
      type="warning"
      :closable="true"
      :title="`无权访问：${route.query.denied}`"
      style="margin-bottom: 12px"
    />

    <PageAsyncState v-if="loadError" state="error" :errorMessage="loadError" />
    <template v-else>
    <el-row :gutter="16">
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never" class="stat-card clickable" @click="go('/tasks', { status: 'queued' })">
          <div class="stat-label">进行中任务</div>
          <div class="stat-value">{{ stats.running_task_count ?? workbench.running?.length ?? 0 }}</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never" class="stat-card clickable" @click="go('/agents')">
          <div class="stat-label">待确认编排</div>
          <div class="stat-value">{{ workbench.pending_approvals ?? 0 }}</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never" class="stat-card clickable" @click="go('/tasks', { status: 'pending_review' })">
          <div class="stat-label">待审任务</div>
          <div class="stat-value">{{ workbench.pending_reviews ?? 0 }}</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never" class="stat-card clickable" @click="go('/tasks')">
          <div class="stat-label">评测任务总数</div>
          <div class="stat-value">{{ stats.task_count ?? 0 }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :xs="24" :md="10">
        <el-card shadow="never">
          <template #header>待办</template>
          <el-table v-if="workbench.todos?.length" :data="workbench.todos" size="small">
            <el-table-column prop="kind" label="类型" width="120">
              <template #default="{ row }">{{ kindLabel(row.kind) }}</template>
            </el-table-column>
            <el-table-column prop="title" label="事项" min-width="140" show-overflow-tooltip />
            <el-table-column width="80">
              <template #default="{ row }">
                <el-button link type="primary" @click="$router.push(row.href)">处理</el-button>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState
            v-else
            type="default"
            title="暂无待办"
            description="可以从快捷入口创建评测或导入数据起步。"
            :show-action="false"
          />
        </el-card>
      </el-col>
      <el-col :xs="24" :md="14">
        <el-card shadow="never">
          <template #header>快捷入口</template>
          <div class="shortcuts">
            <el-button
              v-for="s in shortcuts"
              :key="s.path"
              :type="s.primary ? 'primary' : 'default'"
              plain
              @click="go(s.path)"
            >{{ s.label }}</el-button>
          </div>
          <p v-if="!shortcuts.length" class="hint">当前角色无可写入口，请联系管理员授权。</p>
        </el-card>
        <el-card shadow="never" class="mt">
          <template #header>异常任务</template>
          <el-table v-if="workbench.failed?.length" :data="workbench.failed" size="small">
            <el-table-column prop="name" label="任务" />
            <el-table-column prop="error_message" label="原因" show-overflow-tooltip />
            <el-table-column width="80">
              <template #default="{ row }">
                <el-button link type="primary" @click="$router.push(`/tasks/${row.id}`)">查看</el-button>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState
            v-else
            type="default"
            title="暂无异常任务"
            description="失败任务会显示在这里，可从列表进入详情处理。"
            :show-action="false"
          />
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="mt">
      <template #header>最近任务</template>
      <el-table v-if="workbench.recent?.length" :data="workbench.recent" size="small">
        <el-table-column prop="name" label="任务" />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <StatusBadge :phase="taskPhase(row.status)" :text="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="通过率" width="110">
          <template #default="{ row }">
            {{ row.pass_rate == null ? '—' : `${((row.pass_rate || 0) * 100).toFixed(1)}%` }}
          </template>
        </el-table-column>
        <el-table-column label="" width="90">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/tasks/${row.id}`)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
      <EmptyState
        v-else
        type="task"
        action-text="去创建任务"
        :show-action="userStore.hasPermission('task:create')"
        @action="go('/tasks')"
      />
    </el-card>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { dashboardApi } from '@/api'
import { useUserStore } from '@/stores/user'
import EmptyState from '@/components/EmptyState.vue'
import PageAsyncState from '@/components/PageAsyncState.vue'
import StatusBadge from '@/components/StatusBadge.vue'

const userStore = useUserStore()
const router = useRouter()
const route = useRoute()
const stats = ref({})
const workbench = ref({ todos: [], running: [], failed: [], recent: [] })
const loadError = ref('')

const shortcuts = computed(() => {
  const list = []
  if (userStore.hasPermission('agent:invoke')) list.push({ path: '/agents', label: '发起编排评测', primary: true })
  if (userStore.hasPermission('task:create')) list.push({ path: '/tasks', label: '创建任务' })
  if (userStore.hasPermission('dataset:create')) list.push({ path: '/datasets', label: '导入数据' })
  if (userStore.hasPermission('model:create')) list.push({ path: '/models', label: '注册模型' })
  if (userStore.hasPermission('resource:list')) list.push({ path: '/resources', label: '工具中心' })
  if (userStore.hasPermission('service:create')) list.push({ path: '/services', label: '评测服务' })
  return list
})

function kindLabel(k) {
  return ({ task_review: '任务审核', agent_confirm: '编排确认', task_failed: '任务失败' }[k] || k)
}

function taskPhase(st) {
  if (['queued', 'running'].includes(st)) return 'running'
  if (st === 'failed') return 'failed'
  if (st === 'success') return 'completed'
  if (st === 'pending_review') return 'awaiting_approval'
  return 'idle'
}

function go(path, query) {
  router.push({ path, query })
}

onMounted(async () => {
  try {
    stats.value = await dashboardApi.getStats()
    workbench.value = await dashboardApi.getWorkbench()
    loadError.value = ''
  } catch (err) {
    const data = err?.response?.data
    const msg = data?.message ?? data?.detail ?? err?.message
    loadError.value = typeof msg === 'string' && msg ? msg : '工作台加载失败'
  }
})
</script>

<style scoped>
.dashboard-page { display: flex; flex-direction: column; gap: 16px; }
.stat-card { margin-bottom: 0; }
.stat-card.clickable { cursor: pointer; }
.stat-card.clickable:hover { border-color: var(--el-color-primary-light-5); }
.stat-label { color: var(--text-secondary); font-size: 13px; }
.stat-value { margin-top: 8px; font-size: 28px; font-weight: 600; }
.shortcuts { display: flex; flex-wrap: wrap; gap: 8px; }
.hint { color: var(--text-secondary); margin: 0; }
.mt { margin-top: 16px; }
</style>
