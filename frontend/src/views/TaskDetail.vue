<template>
  <div v-loading="loading">
    <div class="page-header">
      <div>
        <h2 class="page-title">{{ task.name || '任务详情' }}</h2>
        <p class="page-desc">{{ task.report_summary || '提交后将按数据分片逐条调用模型与打分工具' }}</p>
      </div>
      <div>
        <el-button v-if="userStore.hasPermission('task:run')" type="primary" :disabled="task.status === 'running'" @click="run">执行</el-button>
        <el-button v-if="task.report_path" @click="download('json')">JSON</el-button>
        <el-button v-if="task.report_path" @click="download('xlsx')">Excel</el-button>
        <el-button v-if="task.report_path" @click="download('docx')">Word</el-button>
        <el-button v-if="task.report_path" @click="download('pdf')">PDF</el-button>
      </div>
    </div>
    <el-row :gutter="16" class="block">
      <el-col :span="6"><el-card><div class="stat-label">状态</div><div class="stat-value">{{ task.status }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="stat-label">进度</div><div class="stat-value">{{ task.progress || 0 }}%</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="stat-label">通过率</div><div class="stat-value">{{ ((task.pass_rate || 0) * 100).toFixed(1) }}%</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="stat-label">平均分</div><div class="stat-value">{{ Number(task.avg_score || 0).toFixed(3) }}</div></el-card></el-col>
    </el-row>
    <el-descriptions :column="3" border class="block">
      <el-descriptions-item label="模板">{{ task.template_code || '-' }}</el-descriptions-item>
      <el-descriptions-item label="场景">{{ task.scene }}</el-descriptions-item>
      <el-descriptions-item label="行业">{{ task.industry }}</el-descriptions-item>
      <el-descriptions-item label="优先级">{{ task.priority }}</el-descriptions-item>
      <el-descriptions-item label="依赖">{{ task.depends_on_id || '-' }}</el-descriptions-item>
      <el-descriptions-item label="工具版本">{{ task.tool_version || '-' }}</el-descriptions-item>
      <el-descriptions-item label="血缘 checksum">{{ lineage.checksum || '-' }}</el-descriptions-item>
      <el-descriptions-item label="通道">{{ lineage.channel_type || '-' }}</el-descriptions-item>
      <el-descriptions-item label="trace">{{ lineage.trace_id || '-' }}</el-descriptions-item>
    </el-descriptions>
    <el-card class="block">
      <template #header>子任务分片</template>
      <el-table :data="subtasks" stripe size="small">
        <el-table-column prop="shard_no" label="分片" width="80" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column label="样本" width="140">
          <template #default="{ row }">{{ row.item_from }} - {{ row.item_to }}</template>
        </el-table-column>
        <el-table-column prop="progress" label="进度" width="80" />
      </el-table>
    </el-card>
    <el-card class="block">
      <template #header>事件</template>
      <el-timeline>
        <el-timeline-item v-for="e in events" :key="e.id" :timestamp="e.created_at">
          {{ e.event_type }}
        </el-timeline-item>
      </el-timeline>
    </el-card>
    <el-card>
      <template #header>逐条结果</template>
      <el-table :data="results" stripe>
        <el-table-column prop="item_no" label="#" width="60" />
        <el-table-column prop="input_content" label="输入" min-width="180" show-overflow-tooltip />
        <el-table-column prop="model_output" label="模型输出" min-width="180" show-overflow-tooltip />
        <el-table-column prop="reference_answer" label="参考" min-width="140" show-overflow-tooltip />
        <el-table-column prop="score" label="得分" width="80" />
        <el-table-column prop="passed" label="通过" width="80">
          <template #default="{ row }">{{ row.passed ? '是' : '否' }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { tasksApi } from '@/api'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const userStore = useUserStore()
const loading = ref(false)
const task = ref({})
const results = ref([])
const events = ref([])
const subtasks = ref([])
const lineage = ref({})
let timer

async function load() {
  task.value = await tasksApi.get(route.params.id)
  const [res, ev, st] = await Promise.all([
    tasksApi.results(route.params.id, { page_size: 100 }),
    tasksApi.events(route.params.id),
    tasksApi.subtasks(route.params.id)
  ])
  results.value = res.items || []
  events.value = ev.items || []
  subtasks.value = st.items || []
  try {
    lineage.value = await tasksApi.lineage(route.params.id)
  } catch {
    lineage.value = {}
  }
}

async function run() {
  await tasksApi.run(route.params.id)
  ElMessage.success('已开始执行')
  load()
}

async function download(fmt = 'json') {
  const blob = await tasksApi.report(route.params.id, { fmt })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `task-${route.params.id}.${fmt}`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  loading.value = true
  try { await load() } finally { loading.value = false }
  timer = setInterval(load, 2000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.block { margin-bottom: 16px; }
.stat-label { color: var(--text-secondary); font-size: 13px; }
.stat-value { margin-top: 8px; font-size: 22px; font-weight: 600; }
</style>
