<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">编排 Agent</h2>
        <p class="page-desc">澄清/审批 → 按需委派 monitor/diagnose → 证据与子任务；知识候选审核后入库。</p>
      </div>
    </div>
    <el-row :gutter="16">
      <el-col :span="8">
        <el-card>
          <template #header>提出需求</template>
          <el-input v-model="requirement" type="textarea" rows="3" placeholder="例如：对金融场景做智能对话正式评测" />
          <el-input v-model="objective" style="margin-top: 8px" placeholder="目标 objective（可同需求）" />
          <el-input-number v-model="tokenBudget" :min="0" style="margin-top: 8px; width: 100%" />
          <div class="hint">token 预算（正式评测建议 >0）</div>
          <el-button v-if="userStore.hasPermission('agent:invoke')" type="primary" style="margin-top: 8px" :loading="creating" @click="createSession">生成计划</el-button>
        </el-card>
        <el-card style="margin-top: 12px">
          <template #header>澄清补全</template>
          <el-form label-width="88px" size="small">
            <el-form-item label="数据集 ID"><el-input-number v-model="clarifyForm.dataset_id" :min="0" /></el-form-item>
            <el-form-item label="模型 ID"><el-input-number v-model="clarifyForm.model_id" :min="0" /></el-form-item>
            <el-form-item label="预算"><el-input-number v-model="clarifyForm.token_budget" :min="0" /></el-form-item>
            <el-form-item label="试用"><el-switch v-model="clarifyForm.trial_run" /></el-form-item>
          </el-form>
          <el-button v-if="userStore.hasPermission('agent:invoke')" :disabled="!currentId" type="primary" @click="clarify">提交澄清</el-button>
        </el-card>
        <el-card style="margin-top: 12px">
          <template #header>
            知识库
            <el-button v-if="userStore.hasPermission('agent:list')" link type="primary" size="small" style="float: right" @click="loadCandidates">候选</el-button>
          </template>
          <el-table :data="knowledge" size="small" max-height="160">
            <el-table-column prop="category" label="类" width="80" />
            <el-table-column prop="title" label="条目" show-overflow-tooltip />
          </el-table>
          <el-table v-if="candidates.length" :data="candidates" size="small" style="margin-top: 8px" max-height="140">
            <el-table-column prop="id" label="#" width="50" />
            <el-table-column prop="title" label="候选" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="80" />
            <el-table-column width="100">
              <template #default="{ row }">
                <el-button v-if="userStore.hasPermission('agent:confirm') && row.status === 'pending'" link type="primary" @click="reviewCand(row, true)">通过</el-button>
              </template>
            </el-table-column>
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
            <div>状态 <strong>{{ session.status }}</strong> · hash {{ (session.plan.canonical_hash || '').slice(0, 12) }}…</div>
            <div>模板 {{ session.plan.template_code }} · 数据 {{ session.plan.dataset_id }} · 模型 {{ session.plan.model_id }} · trial {{ session.plan.trial_run }} · budget {{ session.plan.token_budget }}</div>
            <div v-if="session.plan.goal_spec">Goal：{{ session.plan.goal_spec.objective }}</div>
            <div v-if="session.plan.clarifications?.length" class="warn">
              澄清：
              <ul>
                <li v-for="(c, i) in session.plan.clarifications" :key="i">{{ c.question }}</li>
              </ul>
            </div>
            <div v-if="session.plan.resource_gaps?.length" class="warn">资源缺口：{{ session.plan.resource_gaps.join('；') }}</div>
            <div v-if="session.plan.validation_errors?.length" class="warn">校验：{{ session.plan.validation_errors.join('；') }}</div>
          </div>
          <div class="msgs">
            <div v-for="m in session.messages || []" :key="m.id" class="msg">
              <b>{{ m.role }}</b> {{ m.content }}
            </div>
          </div>
          <div class="actions">
            <el-button v-if="userStore.hasPermission('agent:confirm')" :disabled="!session.plan?.ready" @click="approve">签发审批</el-button>
            <el-button v-if="userStore.hasPermission('agent:confirm')" type="primary" :disabled="!canConfirm" @click="confirm(true)">确认并执行</el-button>
            <el-button v-if="userStore.hasPermission('agent:view')" :disabled="!session.task_id" @click="monitor">监控</el-button>
            <el-button v-if="userStore.hasPermission('agent:invoke')" :disabled="!session.task_id" @click="diagnose">诊断</el-button>
            <el-button v-if="userStore.hasPermission('agent:invoke')" :disabled="!session.task_id" @click="collaborate">按需协作</el-button>
            <el-button v-if="userStore.hasPermission('agent:invoke')" :disabled="!currentId" :loading="runLoading" @click="startRuntime">启动 Runtime</el-button>
          </div>
          <el-table v-if="delegations.length" :data="delegations" size="small" style="margin-top: 12px">
            <el-table-column prop="id" label="子任务" width="70" />
            <el-table-column prop="role" label="角色" width="100" />
            <el-table-column prop="status" label="状态" width="90" />
            <el-table-column prop="depth" label="深度" width="60" />
            <el-table-column prop="budget_slice" label="预算片" width="80" />
          </el-table>
          <el-table v-if="evidence.length" :data="evidence" size="small" style="margin-top: 8px" max-height="180">
            <el-table-column prop="role" label="来源" width="90" />
            <el-table-column prop="type" label="证据类型" width="120" />
            <el-table-column prop="ref" label="引用" min-width="140" show-overflow-tooltip />
            <el-table-column prop="value" label="值" min-width="120" show-overflow-tooltip />
          </el-table>
          <el-table v-if="session.approvals?.length" :data="session.approvals" size="small" style="margin-top: 12px">
            <el-table-column prop="id" label="审批" width="70" />
            <el-table-column prop="status" label="状态" width="100" />
            <el-table-column prop="plan_hash" label="plan_hash" min-width="140" show-overflow-tooltip />
            <el-table-column prop="expires_at" label="过期" min-width="120" />
            <el-table-column prop="consumed_task_id" label="任务" width="80" />
          </el-table>
          <el-card v-if="run" shadow="never" class="run-card">
            <p>
              run #{{ run.id }} · <strong>{{ run.status }}</strong>
              · rounds {{ run.rounds_used }}/{{ run.max_rounds }}
              · tokens {{ run.tokens_used }}/{{ run.token_budget || '∞' }}
              <span v-if="run.error_code"> · {{ run.error_code }}</span>
            </p>
            <div class="actions">
              <el-button size="small" @click="refreshRun">刷新</el-button>
              <el-button v-if="userStore.hasPermission('agent:invoke') && !['success','cancelled'].includes(run.status)" size="small" @click="cancelRuntime">取消</el-button>
              <el-button v-if="userStore.hasPermission('agent:invoke') && ['waiting','failed','queued'].includes(run.status)" size="small" type="primary" @click="resumeRuntime">从 checkpoint 恢复</el-button>
            </div>
            <el-timeline style="margin-top: 12px; max-height: 200px; overflow: auto">
              <el-timeline-item v-for="e in events" :key="e.seq" :timestamp="`#${e.seq}`" placement="top">
                <b>{{ e.type }}</b>
                <span v-if="e.step_id"> · {{ e.step_id }}</span>
              </el-timeline-item>
            </el-timeline>
          </el-card>
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
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { agentsApi } from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const requirement = ref('金融行业智能对话评测')
const objective = ref('产出可执行评测计划')
const tokenBudget = ref(0)
const creating = ref(false)
const knowledge = ref([])
const sessions = ref([])
const currentId = ref(null)
const session = ref({})
const approvalId = ref(null)
const run = ref(null)
const events = ref([])
const runLoading = ref(false)
const clarifyForm = ref({ dataset_id: 0, model_id: 0, token_budget: 0, trial_run: true })
const delegations = ref([])
const evidence = ref([])
const candidates = ref([])
let eventCursor = 0
let pollTimer

const canConfirm = computed(() => {
  if (!session.value?.plan?.ready) return false
  return ['waiting_confirm', 'approved', 'planning'].includes(session.value.status) || !!approvalId.value
})

async function loadList() {
  const [k, s] = await Promise.all([agentsApi.knowledge(), agentsApi.sessions()])
  knowledge.value = k.items || []
  sessions.value = s.items || []
}

async function loadCandidates() {
  const res = await agentsApi.knowledgeCandidates({ status: 'pending' })
  candidates.value = res.items || []
}

async function reviewCand(row, approve) {
  await agentsApi.reviewKnowledge(row.id, { approve, ttl_days: 365 })
  ElMessage.success(approve ? '已入库' : '已拒绝')
  await loadCandidates()
  await loadList()
}

async function loadSession() {
  if (!currentId.value) return
  session.value = await agentsApi.getSession(currentId.value)
  const ap = (session.value.approvals || []).find((a) => a.status === 'approved')
  approvalId.value = ap?.id || (session.value.approvals || [])[0]?.id || null
  if (session.value.active_run_id) await loadRun(session.value.active_run_id)
  if (session.value.task_id) await loadDelegations()
}

async function loadDelegations() {
  if (!currentId.value) return
  const res = await agentsApi.delegations(currentId.value)
  delegations.value = res.items || []
  evidence.value = res.evidence || []
}

async function createSession() {
  creating.value = true
  try {
    const created = await agentsApi.createSession({
      requirement: requirement.value,
      objective: objective.value || requirement.value,
      token_budget: tokenBudget.value || 0,
    })
    ElMessage.success(created.plan?.ready ? '计划已就绪，可审批' : '需要澄清')
    await loadList()
    currentId.value = created.id
    await loadSession()
  } finally {
    creating.value = false
  }
}

async function clarify() {
  const payload = {
    objective: objective.value || requirement.value,
    trial_run: clarifyForm.value.trial_run,
    token_budget: clarifyForm.value.token_budget,
  }
  if (clarifyForm.value.dataset_id) payload.dataset_id = clarifyForm.value.dataset_id
  if (clarifyForm.value.model_id) payload.model_id = clarifyForm.value.model_id
  await agentsApi.clarify(currentId.value, payload)
  ElMessage.success('已更新计划（旧审批将失效）')
  await loadSession()
}

async function approve() {
  const res = await agentsApi.approve(currentId.value, { ttl_minutes: 30 })
  approvalId.value = res.approval?.id
  ElMessage.success(`审批 #${approvalId.value}`)
  await loadSession()
}

async function confirm(execute) {
  const inv = `ui-${currentId.value}-${Date.now()}`
  const res = await agentsApi.confirm(currentId.value, {
    execute,
    approval_id: approvalId.value || undefined,
    client_invocation_id: inv,
  })
  ElMessage.success(res.idempotent ? `幂等返回任务 #${res.task_id}` : `已创建任务 #${res.task_id}`)
  await loadSession()
}

async function monitor() {
  await agentsApi.monitor(currentId.value)
  await loadSession()
  await loadDelegations()
}

async function diagnose() {
  await agentsApi.diagnose(currentId.value)
  await loadSession()
  await loadDelegations()
}

async function collaborate() {
  const res = await agentsApi.collaborate(currentId.value, {})
  ElMessage.success(`委派角色: ${(res.roles || []).join(',') || '无'}`)
  await loadSession()
  await loadDelegations()
}

async function act(row, accepted) {
  await agentsApi.actSuggestion(row.id, { accepted })
  loadSession()
}

async function loadRun(rid) {
  run.value = await agentsApi.getRun(rid)
  const res = await agentsApi.runEvents(rid, { after_seq: 0 })
  events.value = res.items || []
  eventCursor = run.value.event_seq || 0
  startPoll()
}

async function refreshRun() {
  if (!run.value?.id) return
  run.value = await agentsApi.getRun(run.value.id)
  const res = await agentsApi.runEvents(run.value.id, { after_seq: eventCursor })
  if (res.items?.length) {
    events.value = [...events.value, ...res.items]
    eventCursor = res.items[res.items.length - 1].seq
  }
}

async function startRuntime() {
  if (!currentId.value) return
  runLoading.value = true
  try {
    run.value = await agentsApi.startRun(currentId.value, {
      message: requirement.value || session.value.requirement,
      provider: 'mock',
      sync: true,
      max_rounds: 8,
    })
    eventCursor = 0
    events.value = []
    await refreshRun()
    await loadSession()
    ElMessage.success(`run ${run.value.status}`)
  } finally {
    runLoading.value = false
  }
}

async function cancelRuntime() {
  if (!run.value?.id) return
  run.value = await agentsApi.cancelRun(run.value.id)
  await refreshRun()
  ElMessage.success('已取消')
}

async function resumeRuntime() {
  if (!run.value?.id) return
  run.value = await agentsApi.resumeRun(run.value.id)
  await refreshRun()
  await loadSession()
  ElMessage.success(`恢复后 ${run.value.status}`)
}

function startPoll() {
  clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    if (!run.value?.id) return
    if (['success', 'failed', 'cancelled', 'paused_budget'].includes(run.value.status)) {
      clearInterval(pollTimer)
      return
    }
    await refreshRun()
  }, 2000)
}

onMounted(loadList)
onUnmounted(() => clearInterval(pollTimer))
</script>

<style scoped>
.plan { color: var(--el-text-color-secondary); margin-bottom: 8px; font-size: 13px; line-height: 1.5; }
.plan .warn { color: var(--el-color-warning); margin-top: 4px; }
.plan ul { margin: 4px 0 0 16px; padding: 0; }
.msgs { min-height: 80px; margin-bottom: 12px; }
.msg { margin: 6px 0; font-size: 13px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.run-card { margin-top: 12px; font-size: 13px; }
.run-card p { margin: 0 0 8px; }
.hint { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }
</style>
