<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">运行支撑</h2>
        <p class="page-desc">健康检查、进程内 Prometheus 指标、SQLite 备份、快照 GC 与厂商接入基础验收。默认远程加密评测。</p>
      </div>
      <div>
        <el-button v-if="userStore.hasPermission('ops:backup')" :loading="gcing" @click="gc">清理过期快照</el-button>
        <el-button v-if="userStore.hasPermission('ops:backup')" type="primary" :loading="backing" @click="backup">立即备份</el-button>
      </div>
    </div>
    <el-row :gutter="16" class="block">
      <el-col :span="6"><el-card><div class="stat-label">环境</div><div class="stat-value">{{ status.env || '-' }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="stat-label">mTLS 证书</div><div class="stat-value">{{ status.mtls_configured ? '已配置' : '未配置' }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="stat-label">审计保留</div><div class="stat-value">{{ status.audit_retention_days || 180 }} 天</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="stat-label">评测完成</div><div class="stat-value">{{ status.metrics?.eval_completed ?? 0 }}</div></el-card></el-col>
    </el-row>
    <el-descriptions :column="2" border class="block">
      <el-descriptions-item label="备份目录">{{ status.backup_dir || '-' }}</el-descriptions-item>
      <el-descriptions-item label="HTTP 请求">{{ status.metrics?.http_requests ?? 0 }}</el-descriptions-item>
      <el-descriptions-item label="模型调用">{{ status.metrics?.model_invokes ?? 0 }}</el-descriptions-item>
      <el-descriptions-item label="调用失败">{{ status.metrics?.model_invoke_failures ?? 0 }}</el-descriptions-item>
    </el-descriptions>
    <el-card class="block">
      <template #header>基础级交付验收</template>
      <el-table :data="acceptance.items || []" size="small">
        <el-table-column prop="name" label="项" min-width="160" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">{{ row.ok ? '通过' : '未齐' }}</template>
        </el-table-column>
        <el-table-column prop="detail" label="说明" min-width="220" />
      </el-table>
    </el-card>
    <el-card class="block">
      <template #header>告警策略</template>
      <el-table :data="alerts" size="small">
        <el-table-column prop="title" label="策略" min-width="160" />
        <el-table-column prop="event_type" label="事件" width="140" />
        <el-table-column label="启用" width="100">
          <template #default="{ row }">
            <el-switch
              v-if="userStore.hasPermission('task:edit')"
              :model-value="row.enabled"
              @change="(v) => toggleAlert(row, v)"
            />
            <span v-else>{{ row.enabled ? '开' : '关' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    <el-card>
      <template #header>Prometheus 文本</template>
      <pre class="metrics">{{ metricsText || '加载中…' }}</pre>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { opsApi, tasksApi } from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const status = ref({})
const metricsText = ref('')
const backing = ref(false)
const gcing = ref(false)
const acceptance = ref({})
const alerts = ref([])

async function load() {
  const [st, acc, al] = await Promise.all([
    opsApi.status(),
    opsApi.acceptance(),
    tasksApi.alerts()
  ])
  status.value = st
  acceptance.value = acc
  alerts.value = al.items || []
  metricsText.value = await opsApi.metrics()
}

async function backup() {
  backing.value = true
  try {
    const r = await opsApi.backup()
    ElMessage.success(`已备份到 ${r.path}`)
    await load()
  } finally {
    backing.value = false
  }
}

async function gc() {
  gcing.value = true
  try {
    const r = await opsApi.gcSnapshots()
    ElMessage.success(`已清理 ${r.removed} 个过期快照`)
  } finally {
    gcing.value = false
  }
}

async function toggleAlert(row, enabled) {
  await tasksApi.patchAlert(row.id, { enabled })
  row.enabled = enabled
}

onMounted(load)
</script>

<style scoped>
.block { margin-bottom: 16px; }
.stat-label { color: var(--text-secondary); font-size: 13px; }
.stat-value { margin-top: 8px; font-size: 20px; font-weight: 600; }
.metrics { white-space: pre-wrap; font-size: 12px; max-height: 360px; overflow: auto; margin: 0; }
</style>
