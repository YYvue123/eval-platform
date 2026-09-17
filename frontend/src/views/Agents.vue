<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">编排 Agent</h2>
        <p class="page-desc">主 Agent 出计划，监控/诊断只分析。创建、改配、恢复必须校验并人工确认后走工具，不直接改调度。</p>
      </div>
    </div>
    <el-row :gutter="16">
      <el-col :span="8">
        <el-card>
          <template #header>提出需求</template>
          <el-input v-model="requirement" type="textarea" rows="4" placeholder="例如：对金融场景做智能对话正式评测" />
          <el-button v-if="userStore.hasPermission('agent:invoke')" type="primary" style="margin-top: 8px" :loading="creating" @click="createSession">生成计划</el-button>
        </el-card>
        <el-card style="margin-top: 12px">
          <template #header>知识库</template>
          <el-table :data="knowledge" size="small" max-height="280">
            <el-table-column prop="category" label="类" width="80" />
            <el-table-column prop="title" label="条目" show-overflow-tooltip />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="16">
        <el-card>
          <template #header>
            会话
            <el-select v-model="currentId" placeholder="选择会话" style="width: 220px; margin-left: 12px" @change="loadSession">
              <el-option v-for="s in sessions" :key="s.id" :label="`#${s.id} ${s.title}`" :value="s.id" />
            </el-select>
          </template>
          <div v-if="session.plan" class="plan">
            模板 {{ session.plan.template_code }} · 数据 {{ session.plan.dataset_id }} · 模型 {{ session.plan.model_id }}
            <span v-if="session.plan.validation_errors?.length"> · 校验：{{ session.plan.validation_errors.join('；') }}</span>
          </div>
          <div class="msgs">
            <div v-for="m in session.messages || []" :key="m.id" class="msg">
              <b>{{ m.role }}</b> {{ m.content }}
            </div>
          </div>
          <div class="actions">
            <el-button v-if="userStore.hasPermission('agent:confirm')" type="primary" :disabled="session.status !== 'waiting_confirm'" @click="confirm(true)">确认并执行</el-button>
            <el-button v-if="userStore.hasPermission('agent:view')" :disabled="!session.task_id" @click="monitor">监控</el-button>
            <el-button v-if="userStore.hasPermission('agent:invoke')" :disabled="!session.task_id" @click="diagnose">诊断</el-button>
          </div>
          <el-table v-if="session.suggestions?.length" :data="session.suggestions" size="small" style="margin-top: 12px">
            <el-table-column prop="action" label="建议" width="120" />
            <el-table-column prop="reason" label="原因" />
            <el-table-column prop="status" label="状态" width="90" />
            <el-table-column width="120">
              <template #default="{ row }">
                <el-button v-if="userStore.hasPermission('agent:confirm') && row.status === 'pending'" link type="primary" @click="act(row, true)">采纳</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { agentsApi } from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const requirement = ref('金融行业智能对话评测')
const creating = ref(false)
const knowledge = ref([])
const sessions = ref([])
const currentId = ref(null)
const session = ref({})

async function loadList() {
  const [k, s] = await Promise.all([agentsApi.knowledge(), agentsApi.sessions()])
  knowledge.value = k.items || []
  sessions.value = s.items || []
}

async function loadSession() {
  if (!currentId.value) return
  session.value = await agentsApi.getSession(currentId.value)
}

async function createSession() {
  creating.value = true
  try {
    const created = await agentsApi.createSession({ requirement: requirement.value })
    ElMessage.success(created.status === 'waiting_confirm' ? '计划已生成，请确认' : '计划未就绪')
    await loadList()
    currentId.value = created.id
    await loadSession()
  } finally {
    creating.value = false
  }
}

async function confirm(execute) {
  await agentsApi.confirm(currentId.value, { execute })
  ElMessage.success('已确认，任务将通过工具创建')
  loadSession()
}

async function monitor() {
  await agentsApi.monitor(currentId.value)
  loadSession()
}

async function diagnose() {
  await agentsApi.diagnose(currentId.value)
  loadSession()
}

async function act(row, accepted) {
  await agentsApi.actSuggestion(row.id, { accepted })
  loadSession()
}

onMounted(loadList)
</script>

<style scoped>
.plan { color: var(--el-text-color-secondary); margin-bottom: 8px; font-size: 13px; }
.msgs { min-height: 120px; margin-bottom: 12px; }
.msg { margin: 6px 0; font-size: 13px; }
.actions { display: flex; gap: 8px; }
</style>
