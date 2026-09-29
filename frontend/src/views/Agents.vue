<template>
  <div class="agents-wb">
    <div class="page-header">
      <div>
        <h2 class="page-title">评测助手</h2>
        <p class="page-desc">描述目标、核对计划、批准后执行；执行状态以服务端为准。</p>
      </div>
    </div>

    <div class="wb-layout">
      <aside class="session-rail" :class="{ collapsed: railCollapsed }">
        <div class="rail-head">
          <span>会话</span>
          <el-button link size="small" @click="railCollapsed = !railCollapsed">{{ railCollapsed ? '展开' : '收起' }}</el-button>
        </div>
        <template v-if="!railCollapsed">
          <el-button
            v-if="userStore.hasPermission('agent:invoke')"
            type="primary"
            plain
            class="new-btn"
            @click="startNew"
          >新建评测</el-button>
          <div v-if="sessionsLoadError" class="rail-empty">{{ sessionsLoadError }}</div>
          <div v-else-if="!sessions.length" class="rail-empty">暂无会话</div>
          <button
            v-for="s in sessions"
            :key="s.id"
            type="button"
            class="sess-item"
            :class="{ active: currentId === s.id }"
            @click="selectSession(s.id)"
          >
            <div class="sess-title">#{{ s.id }} {{ s.title || '未命名' }}</div>
            <div class="sess-meta">{{ s.status }}</div>
          </button>
        </template>
      </aside>

      <main class="main-pane">
        <!-- 无会话：起步 -->
        <section v-if="!currentId" class="hero-card">
          <h3>描述你想完成的评测</h3>
          <el-input
            v-model="goalText"
            type="textarea"
            :rows="4"
            placeholder="例如：对金融场景做智能对话正式评测，使用已发布数据集与已配置连接的模型"
          />
          <div class="prep">
            <div class="prep-row">
              <span>规划模型（Runtime）</span>
              <StatusBadge v-if="plannerModels.length" phase="approved" text="已配置" />
              <StatusBadge v-else phase="failed" text="真实模型未配置" />
              <router-link v-if="userStore.hasPermission('model:create')" class="link" to="/models">去配置模型</router-link>
            </div>
            <div class="prep-row hint">配置完成前不可启动 Runtime；正式评测还需数据集与被测模型。</div>
          </div>
          <el-collapse>
            <el-collapse-item title="高级：预算与规划模型" name="adv">
              <el-form label-width="100px" size="small">
                <el-form-item label="Token 预算">
                  <el-input-number v-model="tokenBudget" :min="0" />
                  <div class="hint">0 表示后端按未设限额处理；正式评测建议 &gt;0</div>
                </el-form-item>
                <el-form-item label="规划模型">
                  <el-select v-model="plannerModelId" clearable filterable placeholder="必选" style="width: 100%">
                    <el-option v-for="m in plannerModels" :key="m.id" :label="`#${m.id} ${m.name}`" :value="m.id" />
                  </el-select>
                  <div v-if="modelsLoadError" class="hint">{{ modelsLoadError }}</div>
                </el-form-item>
              </el-form>
            </el-collapse-item>
          </el-collapse>
          <el-button
            v-if="userStore.hasPermission('agent:invoke')"
            type="primary"
            :loading="creating"
            :disabled="!goalText.trim() || !plannerModelId"
            @click="createSession"
          >生成计划</el-button>
        </section>

        <template v-else>
          <div class="main-head">
            <div>
              <h3 class="sess-heading">{{ session.title || `会话 #${currentId}` }}</h3>
              <div class="head-meta">
                <StatusBadge :phase="productPhase" />
                <el-tag v-if="session.plan?.trial_run" size="small" type="info">试跑</el-tag>
                <el-tag v-else-if="session.plan?.ready" size="small">正式</el-tag>
                <span v-if="session.plan?.token_budget != null" class="hint">预算 {{ session.plan.token_budget }}</span>
                <span v-if="pollError" class="warn-inline">{{ pollError }}</span>
              </div>
            </div>
            <div class="head-actions">
              <el-button size="small" @click="drawerOpen = true">计划 / 证据</el-button>
              <el-button size="small" @click="showAdvanced = !showAdvanced">{{ showAdvanced ? '收起高级' : '高级' }}</el-button>
            </div>
          </div>

          <div v-if="sessionLoading" class="hint">加载会话…</div>

          <div class="msgs">
            <div v-for="m in session.messages || []" :key="m.id" class="msg" :class="m.role">
              <b>{{ roleLabel(m.role) }}</b>
              <span>{{ m.content }}</span>
            </div>
          </div>

          <!-- 计划摘要卡 -->
          <el-card v-if="session.plan" shadow="never" class="plan-card">
            <div class="plan-title">计划摘要</div>
            <ul class="plan-list">
              <li>目标：{{ session.plan.goal_spec?.objective || session.requirement }}</li>
              <li>模板 {{ session.plan.template_code || '—' }} · 场景 {{ session.plan.scene || '—' }}</li>
              <li>
                数据
                <strong>{{ datasetLabel }}</strong>
                · 模型
                <strong>{{ modelLabel }}</strong>
              </li>
              <li>模式：{{ session.plan.trial_run ? '试跑' : '正式' }} · 预算 {{ session.plan.token_budget ?? 0 }}</li>
            </ul>
            <el-collapse>
              <el-collapse-item title="技术详情（hash）" name="hash">
                <code>{{ session.plan.canonical_hash || '—' }}</code>
              </el-collapse-item>
            </el-collapse>
            <div v-if="session.plan.resource_gaps?.length" class="warn">
              资源缺口：
              <template v-for="(g, i) in session.plan.resource_gaps" :key="i">
                {{ g }}
                <router-link v-if="g.includes('模型')" class="link" to="/models">配置模型</router-link>
                <router-link v-else-if="g.includes('数据')" class="link" to="/datasets">配置数据集</router-link>
                <span v-if="i < session.plan.resource_gaps.length - 1">；</span>
              </template>
            </div>
            <div v-if="session.plan.validation_errors?.length" class="warn">校验：{{ session.plan.validation_errors.join('；') }}</div>
          </el-card>

          <!-- 待补充：动态澄清 -->
          <el-card v-if="productPhase === 'needs_input' || productPhase === 'awaiting_approval'" shadow="never" class="clarify-card">
            <div class="plan-title">{{ productPhase === 'needs_input' ? '需要补充' : '修改计划（提交后旧审批失效）' }}</div>
            <el-form label-width="100px" size="small">
              <el-form-item
                v-for="c in dynamicClarifications"
                :key="c.field + c.question"
                :label="fieldLabel(c.field)"
              >
                <div class="clarify-q">{{ c.question }}</div>
                <ResourcePicker
                  v-if="c.field === 'dataset_id'"
                  v-model="clarifyForm.dataset_id"
                  kind="dataset"
                  placeholder="搜索数据集"
                />
                <ResourcePicker
                  v-else-if="c.field === 'model_id'"
                  v-model="clarifyForm.model_id"
                  kind="model"
                  placeholder="搜索被测模型"
                />
                <el-input-number
                  v-else-if="c.field === 'token_budget'"
                  v-model="clarifyForm.token_budget"
                  :min="0"
                />
                <el-switch
                  v-else-if="c.field === 'trial_run' || (c.field === 'token_budget' && false)"
                  v-model="clarifyForm.trial_run"
                />
                <el-input
                  v-else-if="c.field === 'objective'"
                  v-model="goalText"
                  type="textarea"
                  :rows="2"
                />
                <div v-else class="hint">请在下方选择资源或调整试用开关后提交</div>
              </el-form-item>
              <el-form-item label="试用模式">
                <el-switch v-model="clarifyForm.trial_run" />
                <span class="hint">开启后按小规模真实样本执行，用量计入同一预算。</span>
              </el-form-item>
              <el-form-item v-if="!hasClarifyField('dataset_id')" label="数据集">
                <ResourcePicker v-model="clarifyForm.dataset_id" kind="dataset" />
              </el-form-item>
              <el-form-item v-if="!hasClarifyField('model_id')" label="被测模型">
                <ResourcePicker v-model="clarifyForm.model_id" kind="model" />
              </el-form-item>
            </el-form>
          </el-card>

          <!-- 主动作条 -->
          <div class="primary-bar">
            <el-button
              v-if="primaryAction"
              type="primary"
              :loading="primaryLoading"
              :disabled="primaryDisabled"
              @click="runPrimary"
            >{{ primaryAction.label }}</el-button>
            <el-button
              v-for="a in secondaryActions"
              :key="a.key"
              :loading="a.loading?.value"
              :disabled="a.disabled"
              @click="a.run"
            >{{ a.label }}</el-button>
            <span v-if="primaryHint" class="hint">{{ primaryHint }}</span>
          </div>

          <!-- 执行时间线 / 结果 -->
          <el-card v-if="run" shadow="never" class="run-card">
            <div class="plan-title">
              执行 · run #{{ run.id }}
              <StatusBadge :phase="runPhase" :text="run.status" />
            </div>
            <p class="hint">
              轮次 {{ run.rounds_used }}/{{ run.max_rounds }}
              · tokens {{ run.tokens_used }}/{{ run.token_budget || '未限额' }}
              <span v-if="run.tokens_usage_unknown"> · usage 未知</span>
              <span v-if="run.error_code"> · {{ run.error_code }}: {{ run.error_message }}</span>
              <span v-if="eventsUpdatedAt"> · 更新 {{ eventsUpdatedAt }}</span>
            </p>
            <el-timeline class="timeline">
              <el-timeline-item v-for="e in events" :key="`${run.id}-${e.seq}`" :timestamp="`#${e.seq}`" placement="top">
                <b>{{ eventLabel(e.type) }}</b>
                <el-collapse v-if="e.payload && Object.keys(e.payload).length">
                  <el-collapse-item title="详情" :name="String(e.seq)">
                    <pre class="payload">{{ formatPayload(e.payload) }}</pre>
                  </el-collapse-item>
                </el-collapse>
              </el-timeline-item>
            </el-timeline>
          </el-card>

          <el-card v-if="session.task_id && productPhase === 'completed'" shadow="never" class="result-card">
            <div class="plan-title">结果</div>
            <p>已关联任务 #{{ session.task_id }}（{{ session.plan?.trial_run ? '试跑' : '正式' }}）</p>
            <el-button type="primary" link @click="$router.push(`/tasks/${session.task_id}`)">查看任务 / 报告</el-button>
            <el-button link @click="startNew">基于此目标新建</el-button>
          </el-card>

          <!-- 高级：Runtime / 知识 / 委派 -->
          <el-card v-if="showAdvanced" shadow="never" class="adv-card">
            <el-tabs>
              <el-tab-pane label="Runtime">
                <el-form label-width="100px" size="small">
                  <el-form-item label="规划模型">
                    <el-select v-model="plannerModelId" clearable filterable placeholder="必选" style="width: 100%">
                      <el-option v-for="m in plannerModels" :key="m.id" :label="`#${m.id} ${m.name}`" :value="m.id" />
                    </el-select>
                    <div v-if="modelsLoadError" class="hint">{{ modelsLoadError }}</div>
                  </el-form-item>
                </el-form>
                <el-button
                  v-if="userStore.hasPermission('agent:invoke')"
                  :loading="runLoading"
                  :disabled="!plannerModelId"
                  @click="startRuntime"
                >启动 Runtime 工具循环</el-button>
                <el-button
                  v-if="run && userStore.hasPermission('agent:invoke') && !['success','cancelled'].includes(run.status)"
                  :loading="cancelLoading"
                  @click="cancelRuntime"
                >{{ cancelLoading ? '取消中…' : '取消 run' }}</el-button>
                <el-button
                  v-if="run && userStore.hasPermission('agent:invoke') && ['waiting','failed','queued'].includes(run.status)"
                  type="primary"
                  :loading="resumeLoading"
                  @click="resumeRuntime"
                >从 checkpoint 恢复</el-button>
              </el-tab-pane>
              <el-tab-pane label="知识候选">
                <el-button size="small" @click="loadCandidates">刷新</el-button>
                <el-table :data="candidates" size="small" style="margin-top: 8px">
                  <el-table-column prop="id" label="#" width="50" />
                  <el-table-column prop="title" label="候选" show-overflow-tooltip />
                  <el-table-column prop="status" label="状态" width="80" />
                  <el-table-column width="90">
                    <template #default="{ row }">
                      <el-button
                        v-if="userStore.hasPermission('agent:confirm') && row.status === 'pending'"
                        link
                        type="primary"
                        @click="reviewCand(row, true)"
                      >通过</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>
              <el-tab-pane label="子任务 / 建议">
                <el-table v-if="delegations.length" :data="delegations" size="small">
                  <el-table-column prop="id" label="子任务" width="70" />
                  <el-table-column prop="role" label="角色" width="100" />
                  <el-table-column prop="status" label="状态" width="90" />
                </el-table>
                <el-table v-if="session.suggestions?.length" :data="session.suggestions" size="small" style="margin-top: 8px">
                  <el-table-column prop="action" label="建议" width="120" />
                  <el-table-column prop="reason" label="原因" />
                  <el-table-column width="100">
                    <template #default="{ row }">
                      <el-button
                        v-if="userStore.hasPermission('agent:confirm') && row.status === 'pending'"
                        link
                        type="primary"
                        @click="act(row, true)"
                      >采纳</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>
            </el-tabs>
          </el-card>
        </template>
      </main>
    </div>

    <el-drawer v-model="drawerOpen" title="计划与证据" size="420px">
      <pre v-if="session.plan" class="payload">{{ JSON.stringify(session.plan, null, 2) }}</pre>
      <el-table v-if="evidence.length" :data="evidence" size="small" style="margin-top: 12px">
        <el-table-column prop="role" label="来源" width="80" />
        <el-table-column prop="type" label="类型" width="100" />
        <el-table-column prop="ref" label="引用" show-overflow-tooltip />
      </el-table>
      <el-table v-if="session.approvals?.length" :data="session.approvals" size="small" style="margin-top: 12px">
        <el-table-column prop="id" label="#" width="50" />
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column prop="expires_at" label="过期" />
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { agentsApi, modelsApi } from '@/api'
import { useUserStore } from '@/stores/user'
import StatusBadge from '@/components/StatusBadge.vue'
import ResourcePicker from '@/components/ResourcePicker.vue'

const userStore = useUserStore()
const route = useRoute()
const router = useRouter()

const railCollapsed = ref(false)
const drawerOpen = ref(false)
const showAdvanced = ref(false)
const goalText = ref('')
const tokenBudget = ref(0)
const plannerModelId = ref(null)
const plannerModels = ref([])
const modelsLoadError = ref('')
const sessionsLoadError = ref('')
const creating = ref(false)
const clarifying = ref(false)
const approving = ref(false)
const confirming = ref(false)
const monitorLoading = ref(false)
const diagnoseLoading = ref(false)
const collabLoading = ref(false)
const runLoading = ref(false)
const cancelLoading = ref(false)
const resumeLoading = ref(false)
const sessionLoading = ref(false)
const sessions = ref([])
const currentId = ref(null)
const session = ref({})
const approvalId = ref(null)
const run = ref(null)
const events = ref([])
const eventsUpdatedAt = ref('')
const pollError = ref('')
const clarifyForm = ref({ dataset_id: null, model_id: null, token_budget: 0, trial_run: true })
const delegations = ref([])
const evidence = ref([])
const candidates = ref([])
const datasetLabel = ref('—')
const modelLabel = ref('—')

let sessionGen = 0
let eventCursor = 0
let seenEventSeq = new Set()
let pollTimer = null
const pollInFlight = ref(false)
let pendingConfirmInvocationId = ''

const dynamicClarifications = computed(() => session.value?.plan?.clarifications || [])

function hasClarifyField(field) {
  return dynamicClarifications.value.some((c) => c.field === field)
}

function fieldLabel(field) {
  return ({ dataset_id: '数据集', model_id: '被测模型', token_budget: '预算', objective: '目标', resource: '资源' }[field] || field)
}

function roleLabel(role) {
  return ({ user: '你', main: '助手', system: '系统', monitor: '监控', diagnose: '诊断' }[role] || role)
}

function eventLabel(type) {
  const map = {
    'run.created': '已创建运行',
    'run.claimed': '已领取执行',
    'llm.select': '规划模型决策',
    'llm.select_none': '无需工具，准备回复',
    'tool.selected': '已选择工具',
    'tool.observed': '工具结果已写入',
    'tool.rejected': '工具参数被拒绝',
    'tool.failed': '工具执行失败',
    'llm.reply': '生成回复',
    'run.success': '运行成功',
    'run.failed': '运行失败',
    'run.cancelled': '已取消',
    'run.paused_budget': '预算暂停',
    'run.resume': '从检查点恢复',
  }
  return map[type] || type
}

function formatPayload(p) {
  try {
    const s = JSON.stringify(p, null, 2)
    return s.length > 2000 ? `${s.slice(0, 2000)}\n…` : s
  } catch {
    return String(p)
  }
}

function isApprovalValid(a, plan) {
  if (!a || a.status !== 'approved') return false
  if (a.consumed_task_id) return false
  if (plan?.canonical_hash && a.plan_hash && a.plan_hash !== plan.canonical_hash) return false
  if (a.expires_at) {
    const exp = Date.parse(a.expires_at)
    if (!Number.isNaN(exp) && exp < Date.now()) return false
  }
  return true
}

const activeApproval = computed(() => {
  const list = session.value?.approvals || []
  return list.find((a) => isApprovalValid(a, session.value?.plan)) || null
})

const TASK_RUNNING = ['draft', 'pending', 'queued', 'running', 'leasing']
const TASK_DONE = ['completed', 'success', 'done']

const productPhase = computed(() => {
  const s = session.value
  const r = run.value
  if (!currentId.value || !s?.id) return 'idle'
  if (r?.status === 'paused_budget') return 'budget_paused'
  if (r?.status === 'cancelled') return 'cancelled'
  if (r?.status === 'failed') return 'failed'
  if (r && ['queued', 'running', 'waiting'].includes(r.status)) return 'running'
  if (s.task_id) {
    const ts = s.task_status || ''
    if (TASK_RUNNING.includes(ts)) return 'running'
    if (ts === 'failed' || ts === 'error') return 'failed'
    if (ts === 'cancelled' || ts === 'canceled') return 'cancelled'
    if (TASK_DONE.includes(ts) && s.report_status === 'available') return 'completed'
    if (TASK_DONE.includes(ts)) return 'report_pending'
    if (!ts) return 'running'
  }
  if (r?.status === 'success' && !s.task_id) return 'completed'
  if (activeApproval.value) return 'approved'
  if (s.plan?.ready && s.status === 'waiting_confirm') return 'awaiting_approval'
  if (s.status === 'approved') return 'approved'
  if (!s.plan?.ready || (s.plan?.clarifications || []).length) return 'needs_input'
  if (s.status === 'planning') return 'planning'
  return 'needs_input'
})

const runPhase = computed(() => {
  const st = run.value?.status
  if (st === 'paused_budget') return 'budget_paused'
  if (st === 'failed') return 'failed'
  if (st === 'success') return 'completed'
  if (['queued', 'running', 'waiting'].includes(st)) return 'running'
  return 'idle'
})

const primaryAction = computed(() => {
  const p = productPhase.value
  if (p === 'needs_input') return { key: 'clarify', label: '补充并更新计划' }
  if (p === 'awaiting_approval') return { key: 'approve', label: '审批计划' }
  if (p === 'approved') return { key: 'confirm', label: '确认并执行' }
  if (p === 'running') return { key: 'view_task', label: '查看任务' }
  if (p === 'failed' && run.value) return { key: 'resume', label: '安全恢复' }
  if (p === 'cancelled') return null
  if (p === 'budget_paused') return null
  if (p === 'report_pending') return { key: 'view_task', label: '查看任务' }
  if (p === 'completed' && session.value?.report_status === 'available') return { key: 'report', label: '查看报告' }
  if (p === 'completed' && session.value?.task_id) return { key: 'view_task', label: '查看任务' }
  return null
})

const primaryLoading = computed(() => {
  const k = primaryAction.value?.key
  if (k === 'clarify') return clarifying.value
  if (k === 'approve') return approving.value
  if (k === 'confirm') return confirming.value
  if (k === 'resume') return resumeLoading.value
  return false
})

const primaryDisabled = computed(() => {
  const k = primaryAction.value?.key
  if (k === 'approve' && !userStore.hasPermission('agent:confirm')) return true
  if (k === 'confirm' && (!userStore.hasPermission('agent:confirm') || !activeApproval.value)) return true
  if (k === 'clarify' && !userStore.hasPermission('agent:invoke')) return true
  return false
})

const primaryHint = computed(() => {
  if (productPhase.value === 'approved' && !activeApproval.value) return '审批已失效，请重新签发'
  if (productPhase.value === 'budget_paused') return '请提高预算后新建 run（后端不支持就地调额）'
  if (primaryAction.value?.key === 'resume' && !['waiting', 'failed', 'queued'].includes(run.value?.status)) {
    return '当前状态不可恢复'
  }
  return ''
})

const secondaryActions = computed(() => {
  const list = []
  const p = productPhase.value
  if (p === 'awaiting_approval' && userStore.hasPermission('agent:invoke')) {
    list.push({
      key: 'edit',
      label: '保存计划修改',
      disabled: clarifying.value,
      loading: clarifying,
      run: clarify,
    })
  }
  if (session.value?.task_id && userStore.hasPermission('agent:view')) {
    list.push({
      key: 'monitor',
      label: '监控',
      disabled: monitorLoading.value,
      loading: monitorLoading,
      run: monitor,
    })
  }
  if (session.value?.task_id && userStore.hasPermission('agent:invoke')) {
    list.push({ key: 'diagnose', label: '诊断', disabled: diagnoseLoading.value, loading: diagnoseLoading, run: diagnose })
    list.push({ key: 'collab', label: '按需协作', disabled: collabLoading.value, loading: collabLoading, run: collaborate })
  }
  return list
})

async function runPrimary() {
  const k = primaryAction.value?.key
  if (k === 'clarify') return clarify()
  if (k === 'approve') return approve()
  if (k === 'confirm') return confirm(true)
  if (k === 'view_task' || k === 'report') {
    if (session.value.task_id) router.push(`/tasks/${session.value.task_id}`)
    return
  }
  if (k === 'resume') return resumeRuntime()
}

function stopPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

function resetRunContext() {
  stopPoll()
  run.value = null
  events.value = []
  eventCursor = 0
  seenEventSeq = new Set()
  eventsUpdatedAt.value = ''
  pollError.value = ''
  pollInFlight.value = false
}

function resetSessionSideState() {
  resetRunContext()
  session.value = {}
  approvalId.value = null
  delegations.value = []
  evidence.value = []
  pendingConfirmInvocationId = ''
  datasetLabel.value = '—'
  modelLabel.value = '—'
}

function loadFailureMessage(err, fallback) {
  const data = err?.response?.data
  const msg = data?.message ?? data?.detail ?? err?.message
  return typeof msg === 'string' && msg ? msg : fallback
}

async function loadList() {
  sessionsLoadError.value = ''
  modelsLoadError.value = ''
  const [sSettled, modelsSettled] = await Promise.allSettled([
    agentsApi.sessions(),
    modelsApi.list({ page: 1, page_size: 100 }),
  ])
  if (sSettled.status === 'fulfilled') {
    sessions.value = sSettled.value.items || []
  } else {
    sessions.value = []
    sessionsLoadError.value = loadFailureMessage(sSettled.reason, '会话列表加载失败')
  }
  if (modelsSettled.status === 'fulfilled') {
    plannerModels.value = (modelsSettled.value.items || []).filter((m) => m.api_url)
  } else {
    plannerModels.value = []
    modelsLoadError.value = loadFailureMessage(modelsSettled.reason, '模型列表加载失败')
  }
}

async function loadCandidates() {
  const res = await agentsApi.knowledgeCandidates({ status: 'pending' })
  candidates.value = res.items || []
}

async function reviewCand(row, approveFlag) {
  await agentsApi.reviewKnowledge(row.id, { approve: approveFlag, ttl_days: 365 })
  ElMessage.success(approveFlag ? '已入库' : '已拒绝')
  await loadCandidates()
}

function startNew() {
  currentId.value = null
  resetSessionSideState()
  router.replace({ path: '/agents', query: {} })
}

function selectSession(id) {
  if (currentId.value === id) return
  currentId.value = id
  router.replace({ path: '/agents', query: { session: String(id) } })
  loadSession()
}

async function resolveLabels(plan, sid, gen) {
  if (gen !== sessionGen || currentId.value !== sid) return
  datasetLabel.value = plan?.dataset_id ? `#${plan.dataset_id}` : '—'
  modelLabel.value = plan?.model_id ? `#${plan.model_id}` : '—'
  try {
    if (plan?.dataset_id) {
      const { datasetsApi } = await import('@/api')
      const d = await datasetsApi.get(plan.dataset_id)
      if (gen !== sessionGen || currentId.value !== sid) return
      datasetLabel.value = d.name || datasetLabel.value
    }
  } catch { /* */ }
  try {
    if (plan?.model_id) {
      const m = await modelsApi.get(plan.model_id)
      if (gen !== sessionGen || currentId.value !== sid) return
      modelLabel.value = m.name || modelLabel.value
    }
  } catch { /* */ }
}

async function loadSession() {
  const sid = currentId.value
  if (!sid) {
    resetSessionSideState()
    return
  }
  const gen = ++sessionGen
  resetSessionSideState()
  sessionLoading.value = true
  try {
    const data = await agentsApi.getSession(sid)
    if (gen !== sessionGen || currentId.value !== sid) return
    session.value = data
    goalText.value = data.requirement || goalText.value
    if (data.plan?.goal_spec?.objective) goalText.value = data.plan.goal_spec.objective
    clarifyForm.value = {
      dataset_id: data.plan?.dataset_id || null,
      model_id: data.plan?.model_id || null,
      token_budget: data.plan?.token_budget || 0,
      trial_run: typeof data.plan?.trial_run === 'boolean' ? data.plan.trial_run : true,
    }
    tokenBudget.value = data.plan?.token_budget || tokenBudget.value
    const valid = (data.approvals || []).find((a) => isApprovalValid(a, data.plan))
    approvalId.value = valid?.id || null
    await resolveLabels(data.plan, sid, gen)
    if (gen !== sessionGen || currentId.value !== sid) return
    if (data.task_id) await loadDelegations(sid, gen)
    const runId = data.active_run_id || data.last_run_id
    if (runId) await loadRun(runId, sid, gen)
  } catch (e) {
    if (gen === sessionGen) ElMessage.error(e?.response?.data?.detail || e?.message || '加载会话失败')
  } finally {
    if (gen === sessionGen) sessionLoading.value = false
  }
}

async function loadDelegations(sid = currentId.value, gen = sessionGen) {
  if (!sid) return
  const res = await agentsApi.delegations(sid)
  if (gen !== sessionGen || currentId.value !== sid) return
  delegations.value = res.items || []
  evidence.value = res.evidence || []
}

async function createSession() {
  if (!plannerModelId.value) {
    ElMessage.warning('请选择规划模型')
    return
  }
  creating.value = true
  try {
    const created = await agentsApi.createSession({
      requirement: goalText.value.trim(),
      objective: goalText.value.trim(),
      token_budget: tokenBudget.value || 0,
    })
    ElMessage.success(created.plan?.ready ? '计划已就绪，可审批' : '需要补充信息')
    await loadList()
    currentId.value = created.id
    router.replace({ path: '/agents', query: { session: String(created.id) } })
    await loadSession()
  } finally {
    creating.value = false
  }
}

async function clarify() {
  if (!currentId.value) return
  clarifying.value = true
  try {
    const payload = {
      objective: goalText.value || session.value.requirement,
      trial_run: clarifyForm.value.trial_run,
      token_budget: clarifyForm.value.token_budget,
    }
    if (clarifyForm.value.dataset_id) payload.dataset_id = clarifyForm.value.dataset_id
    if (clarifyForm.value.model_id) payload.model_id = clarifyForm.value.model_id
    await agentsApi.clarify(currentId.value, payload)
    pendingConfirmInvocationId = ''
    ElMessage.success('计划已更新（旧审批失效）')
    await loadSession()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '澄清失败')
  } finally {
    clarifying.value = false
  }
}

async function approve() {
  if (!currentId.value) return
  approving.value = true
  try {
    const res = await agentsApi.approve(currentId.value, { ttl_minutes: 30 })
    approvalId.value = res.approval?.id
    ElMessage.success(`已签发审批 #${approvalId.value}`)
    await loadSession()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '审批失败')
  } finally {
    approving.value = false
  }
}

async function confirm(execute) {
  if (!currentId.value || !activeApproval.value) {
    ElMessage.warning('需要有效审批')
    return
  }
  confirming.value = true
  try {
    if (!pendingConfirmInvocationId) pendingConfirmInvocationId = `ui-${currentId.value}-${Date.now()}`
    const res = await agentsApi.confirm(currentId.value, {
      execute,
      approval_id: activeApproval.value.id,
      client_invocation_id: pendingConfirmInvocationId,
    })
    pendingConfirmInvocationId = ''
    ElMessage.success(res.idempotent ? `幂等返回任务 #${res.task_id}` : `已创建任务 #${res.task_id}`)
    await loadSession()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '确认失败')
  } finally {
    confirming.value = false
  }
}

async function monitor() {
  monitorLoading.value = true
  try {
    await agentsApi.monitor(currentId.value)
    await loadSession()
  } finally {
    monitorLoading.value = false
  }
}

async function diagnose() {
  diagnoseLoading.value = true
  try {
    await agentsApi.diagnose(currentId.value)
    await loadSession()
  } finally {
    diagnoseLoading.value = false
  }
}

async function collaborate() {
  collabLoading.value = true
  try {
    const res = await agentsApi.collaborate(currentId.value, {})
    ElMessage.success(`委派: ${(res.roles || []).join(',') || '无'}`)
    await loadSession()
  } finally {
    collabLoading.value = false
  }
}

async function act(row, accepted) {
  await agentsApi.actSuggestion(row.id, { accepted })
  await loadSession()
}

function mergeEvents(items, rid) {
  if (!items?.length) return
  for (const e of items) {
    const key = `${rid}:${e.seq}`
    if (seenEventSeq.has(key)) continue
    seenEventSeq.add(key)
    events.value.push(e)
    eventCursor = Math.max(eventCursor, e.seq)
  }
  eventsUpdatedAt.value = new Date().toLocaleTimeString()
}

async function loadRun(rid, sid = currentId.value, gen = sessionGen) {
  resetRunContext()
  const data = await agentsApi.getRun(rid)
  if (gen !== sessionGen || currentId.value !== sid) return
  run.value = data
  const res = await agentsApi.runEvents(rid, { after_seq: 0 })
  if (gen !== sessionGen || currentId.value !== sid) return
  events.value = []
  seenEventSeq = new Set()
  eventCursor = 0
  mergeEvents(res.items || [], rid)
  schedulePoll()
}

async function refreshRun() {
  const rid = run.value?.id
  const sid = currentId.value
  const gen = sessionGen
  if (!rid || pollInFlight.value) return
  pollInFlight.value = true
  try {
    const data = await agentsApi.getRun(rid)
    if (gen !== sessionGen || currentId.value !== sid || run.value?.id !== rid) return
    run.value = data
    const res = await agentsApi.runEvents(rid, { after_seq: eventCursor })
    if (gen !== sessionGen || run.value?.id !== rid) return
    mergeEvents(res.items || [], rid)
    pollError.value = ''
  } catch (e) {
    if (gen === sessionGen) pollError.value = e?.response?.data?.detail || e?.message || '刷新失败'
  } finally {
    pollInFlight.value = false
  }
}

function schedulePoll() {
  stopPoll()
  const tick = async () => {
    if (!run.value?.id) return
    if (['success', 'failed', 'cancelled', 'paused_budget'].includes(run.value.status)) {
      stopPoll()
      return
    }
    await refreshRun()
    if (!run.value?.id) return
    if (['success', 'failed', 'cancelled', 'paused_budget'].includes(run.value.status)) {
      stopPoll()
      return
    }
    pollTimer = setTimeout(tick, 2000)
  }
  pollTimer = setTimeout(tick, 2000)
}

async function startRuntime() {
  if (!currentId.value || !plannerModelId.value) {
    ElMessage.warning('请选择已配置 api_url 的规划模型')
    return
  }
  runLoading.value = true
  const sid = currentId.value
  const gen = sessionGen
  try {
    const data = await agentsApi.startRun(sid, {
      message: goalText.value || session.value.requirement,
      provider: 'live',
      planner_model_id: plannerModelId.value,
      sync: true,
      max_rounds: 8,
    })
    if (gen !== sessionGen || currentId.value !== sid) return
    run.value = data
    events.value = []
    seenEventSeq = new Set()
    eventCursor = 0
    await refreshRun()
    await loadSession()
    ElMessage.success(`run ${run.value?.status}`)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || 'Runtime 失败')
  } finally {
    runLoading.value = false
  }
}

async function cancelRuntime() {
  if (!run.value?.id || cancelLoading.value) return
  cancelLoading.value = true
  try {
    run.value = await agentsApi.cancelRun(run.value.id)
    await refreshRun()
    ElMessage.success(run.value.status === 'cancelled' ? '已取消' : '已请求取消')
    if (!['cancelled', 'success', 'failed'].includes(run.value.status)) schedulePoll()
  } finally {
    cancelLoading.value = false
  }
}

async function resumeRuntime() {
  if (!run.value?.id || resumeLoading.value) return
  resumeLoading.value = true
  try {
    run.value = await agentsApi.resumeRun(run.value.id)
    await refreshRun()
    await loadSession()
    ElMessage.success(`恢复后 ${run.value.status}`)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '恢复失败')
  } finally {
    resumeLoading.value = false
  }
}

watch(
  () => route.query.session,
  (v) => {
    const id = v ? Number(v) : null
    if (id && id !== currentId.value) {
      currentId.value = id
      loadSession()
    }
    if (!v && currentId.value) {
      // keep local selection unless explicitly cleared via startNew
    }
  },
)

onMounted(async () => {
  await loadList()
  const q = route.query.session
  if (q) {
    currentId.value = Number(q)
    await loadSession()
  }
  if (window.innerWidth < 1100) railCollapsed.value = true
})

onUnmounted(() => {
  sessionGen += 1
  stopPoll()
})
</script>

<style scoped>
.agents-wb { --rail-w: 260px; }
.wb-layout { display: flex; gap: 16px; align-items: flex-start; min-height: 60vh; }
.session-rail {
  width: var(--rail-w);
  flex-shrink: 0;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: var(--radius-md, 10px);
  padding: 12px;
}
.session-rail.collapsed { width: 72px; }
.rail-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-weight: 600; }
.new-btn { width: 100%; margin-bottom: 8px; }
.rail-empty { font-size: 12px; color: var(--text-secondary); padding: 8px 0; }
.sess-item {
  display: block; width: 100%; text-align: left; border: none; background: transparent;
  padding: 8px 10px; border-radius: 8px; cursor: pointer; margin-bottom: 4px;
}
.sess-item:hover { background: #f1f5f9; }
.sess-item.active { background: #eef2ff; }
.sess-title { font-size: 13px; font-weight: 600; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sess-meta { font-size: 11px; color: var(--text-secondary); }
.main-pane { flex: 1; min-width: 0; }
.hero-card, .plan-card, .clarify-card, .run-card, .result-card, .adv-card {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: var(--radius-md, 10px);
  padding: 16px;
  margin-bottom: 12px;
}
.hero-card h3 { margin: 0 0 12px; }
.prep { margin: 12px 0; padding: 10px 12px; background: #f8fafc; border-radius: 8px; }
.prep-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; }
.main-head { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.sess-heading { margin: 0 0 6px; font-size: 18px; }
.head-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.msgs { margin-bottom: 12px; }
.msg { padding: 8px 10px; border-radius: 8px; margin-bottom: 6px; font-size: 13px; background: #f8fafc; }
.msg.user { background: #eef2ff; }
.msg b { margin-right: 8px; }
.plan-title { font-weight: 600; margin-bottom: 8px; }
.plan-list { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.7; color: var(--text-secondary); }
.clarify-q { font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; }
.primary-bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 12px 0; }
.timeline { max-height: 280px; overflow: auto; margin-top: 8px; }
.payload { font-size: 11px; white-space: pre-wrap; word-break: break-all; max-height: 240px; overflow: auto; }
.hint { font-size: 12px; color: var(--text-secondary); }
.warn, .warn-inline { color: var(--el-color-warning); font-size: 12px; }
.link { margin-left: 6px; font-size: 12px; }
@media (max-width: 1024px) {
  .wb-layout { flex-direction: column; }
  .session-rail { width: 100%; }
}
</style>
