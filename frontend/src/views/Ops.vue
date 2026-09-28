<template>
  <div class="ops-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">运行支撑</h2>
        <p class="page-desc">探针与准入、工单闭环、演练留痕、数据授权与运营报表。制度版 {{ policy.version || '—' }}。</p>
      </div>
      <div class="actions">
        <el-button v-if="userStore.hasPermission('ops:backup')" :loading="gcing" @click="gc">清理快照</el-button>
        <el-button v-if="userStore.hasPermission('ops:backup')" :loading="backing" @click="backup">立即备份</el-button>
        <el-button v-if="userStore.hasPermission('ops:backup')" :loading="drilling" type="warning" plain @click="drill">恢复演练</el-button>
        <el-button v-if="userStore.hasPermission('ops:admit')" type="primary" :loading="admitting" @click="runAdmission('basic')">基础准入</el-button>
        <el-button v-if="userStore.hasPermission('ops:admit')" type="primary" plain :loading="admitting" @click="runAdmission('full')">完整准入</el-button>
      </div>
    </div>

    <div class="probe-row">
      <div class="probe" :class="liveOk ? 'ok' : 'bad'">
        <div class="probe-k">Liveness</div>
        <div class="probe-v">{{ liveOk ? 'ALIVE' : '—' }}</div>
        <div class="probe-s">/api/live</div>
      </div>
      <div class="probe" :class="readyOk ? 'ok' : 'bad'">
        <div class="probe-k">Readiness</div>
        <div class="probe-v">{{ readyOk ? 'READY' : 'NOT READY' }}</div>
        <div class="probe-s">{{ readyReason || '/api/ready' }}</div>
      </div>
      <div class="probe" :class="status.env === 'production' ? 'prod' : 'dev'">
        <div class="probe-k">环境</div>
        <div class="probe-v">{{ status.env || '—' }}</div>
        <div class="probe-s">开票 {{ report.tickets?.open ?? 0 }} · 演练 {{ report.drills?.total ?? 0 }}</div>
      </div>
      <div class="probe" :class="degraded ? 'bad' : 'ok'">
        <div class="probe-k">降级</div>
        <div class="probe-v">{{ degraded ? 'ACTIVE' : 'CLEAR' }}</div>
        <div class="probe-s">{{ degradeText }}</div>
      </div>
    </div>

    <el-tabs v-model="tab" class="block">
      <el-tab-pane label="准入与探针" name="probe">
        <el-row :gutter="16">
          <el-col :span="14">
            <el-card shadow="never" class="panel">
              <template #header>
                <div class="panel-head">
                  <span>准入验收</span>
                  <el-tag size="small" :type="admissionTagType">{{ admissionLabel }}</el-tag>
                </div>
              </template>
              <div v-if="admission.artifact_hash" class="meta">
                #{{ admission.id }} · {{ admission.level }} · hash {{ shortHash(admission.artifact_hash) }} · {{ admission.elapsed_ms }}ms
              </div>
              <el-table :data="admission.items || []" size="small">
                <el-table-column prop="name" label="项" min-width="150" />
                <el-table-column label="状态" width="100">
                  <template #default="{ row }"><span :class="statusClass(row)">{{ statusText(row) }}</span></template>
                </el-table-column>
                <el-table-column prop="detail" label="说明" min-width="220" />
              </el-table>
            </el-card>
          </el-col>
          <el-col :span="10">
            <el-card shadow="never" class="panel">
              <template #header>恢复演练 / 故障注入</template>
              <el-descriptions :column="1" border size="small">
                <el-descriptions-item label="备份目录">{{ status.backup_dir || '—' }}</el-descriptions-item>
                <el-descriptions-item label="最近演练">
                  <template v-if="drillResult.ok != null">
                    RPO {{ drillResult.rpo_seconds }}s / RTO {{ drillResult.rto_seconds }}s · {{ drillResult.hash_match ? 'hash✓' : 'hash✗' }}
                  </template>
                  <template v-else>—</template>
                </el-descriptions-item>
              </el-descriptions>
              <div class="fault-actions" v-if="userStore.hasPermission('ops:backup')">
                <el-button size="small" @click="injectFault({ db_unavailable: true, reason: 'ui-drill' })">注入 DB 断连</el-button>
                <el-button size="small" @click="injectFault({ cert_expired: true, reason: 'ui-drill' })">注入证书过期</el-button>
                <el-button size="small" type="success" plain @click="injectFault({ clear: true })">清除降级</el-button>
              </div>
            </el-card>
            <el-card shadow="never" class="panel">
              <template #header>告警策略</template>
              <el-table :data="alerts" size="small">
                <el-table-column prop="title" label="策略" min-width="120" />
                <el-table-column prop="event_type" label="事件" width="120" />
                <el-table-column label="启用" width="90">
                  <template #default="{ row }">
                    <el-switch v-if="userStore.hasPermission('task:edit')" :model-value="row.enabled" @change="(v) => toggleAlert(row, v)" />
                    <span v-else>{{ row.enabled ? '开' : '关' }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <el-tab-pane label="工单" name="tickets">
        <div class="toolbar" v-if="userStore.hasPermission('ops:ticket')">
          <el-input v-model="ticketForm.title" placeholder="标题" style="width: 220px" />
          <el-select v-model="ticketForm.category" style="width: 120px">
            <el-option label="故障" value="incident" />
            <el-option label="变更" value="change" />
            <el-option label="漏洞" value="vuln" />
            <el-option label="请求" value="request" />
            <el-option label="一般" value="general" />
          </el-select>
          <el-button type="primary" :loading="ticketSaving" @click="createTicket">建单</el-button>
        </div>
        <el-table :data="tickets" size="small">
          <el-table-column prop="id" label="#" width="60" />
          <el-table-column prop="title" label="标题" min-width="160" />
          <el-table-column prop="category" label="类" width="90" />
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column prop="owner_id" label="负责人" width="90" />
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <template v-if="userStore.hasPermission('ops:ticket') && row.status !== 'disabled'">
                <el-button link type="primary" @click="assignMe(row)">认领</el-button>
                <el-button link type="success" @click="closeTicket(row)">关闭</el-button>
                <el-button link type="info" @click="disableTicket(row)">停用</el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="演练与授权" name="gov">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-card shadow="never" class="panel">
              <template #header>
                <div class="panel-head">
                  <span>演练留痕</span>
                  <el-button v-if="userStore.hasPermission('ops:ticket')" size="small" @click="logDrill">登记 release 演练</el-button>
                </div>
              </template>
              <el-table :data="drills" size="small">
                <el-table-column prop="id" label="#" width="50" />
                <el-table-column prop="drill_type" label="类型" width="90" />
                <el-table-column prop="result" label="结果" width="70" />
                <el-table-column prop="policy_version" label="制度版" min-width="120" />
              </el-table>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card shadow="never" class="panel">
              <template #header>
                <div class="panel-head">
                  <span>数据授权</span>
                  <el-button v-if="userStore.hasPermission('ops:ticket')" size="small" @click="showAuth = true">登记</el-button>
                </div>
              </template>
              <el-table :data="auths" size="small">
                <el-table-column prop="asset_ref" label="资产" min-width="100" />
                <el-table-column prop="license_spdx" label="许可" width="100" />
                <el-table-column prop="grantor" label="授权方" min-width="100" />
                <el-table-column prop="status" label="状态" width="80" />
                <el-table-column label="" width="70">
                  <template #default="{ row }">
                    <el-button
                      v-if="userStore.hasPermission('ops:ticket') && !row.disabled"
                      link
                      type="danger"
                      @click="disableAuth(row)"
                    >停用</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <el-tab-pane label="报表与制度" name="report">
        <el-descriptions :column="2" border class="block">
          <el-descriptions-item label="开票">{{ report.tickets?.open ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="已闭环">{{ report.tickets?.closed ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="演练次数">{{ report.drills?.total ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="有效授权">{{ report.authorizations_active ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="任务总数">{{ report.tasks_total ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="审计条数">{{ report.audit_total ?? 0 }}</el-descriptions-item>
        </el-descriptions>
        <el-card shadow="never" class="panel">
          <template #header>制度索引（仓库路径）</template>
          <el-table :data="policy.docs || []" size="small">
            <el-table-column prop="title" label="标题" width="160" />
            <el-table-column prop="path" label="路径" min-width="280" />
          </el-table>
        </el-card>
        <el-card shadow="never" class="panel">
          <template #header>Prometheus</template>
          <pre class="metrics">{{ metricsText || '加载中…' }}</pre>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="showAuth" title="登记数据授权" width="480px">
      <el-form label-width="96px">
        <el-form-item label="资产引用"><el-input v-model="authForm.asset_ref" /></el-form-item>
        <el-form-item label="SPDX"><el-input v-model="authForm.license_spdx" placeholder="如 LicenseRef-Internal" /></el-form-item>
        <el-form-item label="授权方"><el-input v-model="authForm.grantor" /></el-form-item>
        <el-form-item label="用途"><el-input v-model="authForm.purpose" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAuth = false">取消</el-button>
        <el-button type="primary" :loading="authSaving" @click="createAuth">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { opsApi, tasksApi } from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const tab = ref('probe')
const status = ref({})
const metricsText = ref('')
const backing = ref(false)
const gcing = ref(false)
const drilling = ref(false)
const admitting = ref(false)
const admission = ref({})
const alerts = ref([])
const liveOk = ref(false)
const readyOk = ref(false)
const readyReason = ref('')
const drillResult = ref({})
const tickets = ref([])
const drills = ref([])
const auths = ref([])
const report = ref({})
const policy = ref({})
const ticketSaving = ref(false)
const authSaving = ref(false)
const showAuth = ref(false)
const ticketForm = reactive({ title: '', category: 'incident', detail: '' })
const authForm = reactive({ asset_ref: '', license_spdx: 'LicenseRef-Internal', grantor: '', purpose: '' })

const degraded = computed(() => {
  const d = status.value.degrade || {}
  return !!(d.db_unavailable || d.cert_expired)
})
const degradeText = computed(() => {
  const d = status.value.degrade || {}
  if (!degraded.value) return d.reason || '无注入'
  const parts = []
  if (d.db_unavailable) parts.push('db')
  if (d.cert_expired) parts.push('cert')
  return parts.join('+') + (d.reason ? ` · ${d.reason}` : '')
})
const admissionLabel = computed(() => {
  if (admission.value.ok === true) return '通过'
  if (admission.value.ok === false) return '未通过'
  if (admission.value.ok === null) return '未齐 / 含 unknown'
  return '未跑'
})
const admissionTagType = computed(() => {
  if (admission.value.ok === true) return 'success'
  if (admission.value.ok === false) return 'danger'
  if (admission.value.ok === null) return 'warning'
  return 'info'
})

function shortHash(h) {
  return h ? `${h.slice(0, 10)}…` : '—'
}
function statusText(row) {
  if (row.status === 'unknown') return '未测'
  if (row.ok === true) return '通过'
  if (row.ok === false) return '失败'
  return row.status || '—'
}
function statusClass(row) {
  if (row.status === 'unknown') return 'st-unk'
  if (row.ok === true) return 'st-ok'
  if (row.ok === false) return 'st-bad'
  return ''
}

async function loadProbes() {
  try {
    liveOk.value = !!(await opsApi.live())?.ok
  } catch {
    liveOk.value = false
  }
  try {
    const ready = await opsApi.ready()
    readyOk.value = !!ready?.ok
    readyReason.value = ready?.reason || ''
  } catch (e) {
    readyOk.value = false
    readyReason.value = e?.response?.data?.reason || e?.message || 'error'
  }
}

async function loadGov() {
  const [t, d, a, r, p] = await Promise.all([
    opsApi.tickets(),
    opsApi.drills(),
    opsApi.authorizations({ include_disabled: true }),
    opsApi.report(),
    opsApi.policy()
  ])
  tickets.value = t.items || []
  drills.value = d.items || []
  auths.value = a.items || []
  report.value = r || {}
  policy.value = p || {}
}

async function load() {
  await loadProbes()
  const [st, al] = await Promise.all([opsApi.status(), tasksApi.alerts()])
  status.value = st
  alerts.value = al.items || []
  if (st.last_admission) admission.value = st.last_admission
  else {
    try {
      admission.value = await opsApi.acceptance()
    } catch {
      admission.value = {}
    }
  }
  metricsText.value = await opsApi.metrics()
  await loadGov()
}

async function backup() {
  backing.value = true
  try {
    const r = await opsApi.backup()
    ElMessage.success(`已备份 ${r.path}`)
    await load()
  } finally {
    backing.value = false
  }
}

async function drill() {
  drilling.value = true
  try {
    const r = await opsApi.restoreDrill()
    drillResult.value = r
    if (userStore.hasPermission('ops:ticket')) {
      await opsApi.createDrill({
        drill_type: 'restore',
        result: r.hash_match ? 'pass' : 'fail',
        checklist: ['backup', 'restore-drill', 'hash'],
        evidence: { rpo_seconds: r.rpo_seconds, rto_seconds: r.rto_seconds, sha256: r.sha256 }
      })
    }
    ElMessage.success(`演练完成 RTO=${r.rto_seconds}s`)
    await loadGov()
  } finally {
    drilling.value = false
  }
}

async function runAdmission(level) {
  admitting.value = true
  try {
    admission.value = await opsApi.admissionRun(level)
    ElMessage.success(`准入 ${level} 完成`)
    await load()
  } finally {
    admitting.value = false
  }
}

async function injectFault(body) {
  await opsApi.fault(body)
  ElMessage.success(body.clear ? '已清除降级' : '已注入故障标志')
  await load()
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

async function createTicket() {
  if (!ticketForm.title.trim()) {
    ElMessage.warning('请填写标题')
    return
  }
  ticketSaving.value = true
  try {
    await opsApi.createTicket({ ...ticketForm })
    ticketForm.title = ''
    ElMessage.success('已建单')
    await loadGov()
  } finally {
    ticketSaving.value = false
  }
}

async function assignMe(row) {
  const uid = userStore.userId
  if (!uid) {
    ElMessage.warning('无法获取当前用户，请刷新后重试')
    return
  }
  await opsApi.patchTicket(row.id, { owner_id: uid, status: 'in_progress' })
  ElMessage.success('已认领')
  await loadGov()
}

async function closeTicket(row) {
  const { value } = await ElMessageBox.prompt('填写解决说明（必填）', '关闭工单', {
    inputPlaceholder: 'resolution',
    confirmButtonText: '关闭',
  })
  const uid = userStore.userId
  await opsApi.patchTicket(row.id, {
    status: 'closed',
    resolution: value,
    owner_id: row.owner_id || uid,
  })
  ElMessage.success('已闭环')
  await loadGov()
}

async function disableTicket(row) {
  await opsApi.patchTicket(row.id, { status: 'disabled' })
  ElMessage.success('已停用（记录保留）')
  await loadGov()
}

async function logDrill() {
  await opsApi.createDrill({
    drill_type: 'release',
    result: 'pass',
    checklist: ['ci', 'backup', 'ready', 'admission'],
    notes: 'Ops UI 登记',
  })
  ElMessage.success('已登记演练')
  await loadGov()
}

async function createAuth() {
  authSaving.value = true
  try {
    await opsApi.createAuthorization({ ...authForm, asset_type: 'dataset' })
    showAuth.value = false
    ElMessage.success('已登记授权')
    await loadGov()
  } finally {
    authSaving.value = false
  }
}

async function disableAuth(row) {
  await opsApi.disableAuthorization(row.id)
  ElMessage.success('已停用授权（历史保留）')
  await loadGov()
}

onMounted(load)
</script>

<style scoped>
.ops-page {
  --ops-ink: #0f172a;
  --ops-muted: #64748b;
  --ops-line: #e2e8f0;
  --ops-ok: #059669;
  --ops-bad: #dc2626;
  --ops-warn: #d97706;
  --ops-panel: #f8fafc;
}
.page-header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
.probe-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin: 16px 0;
}
.probe {
  border: 1px solid var(--ops-line);
  border-left: 4px solid var(--ops-muted);
  background: var(--ops-panel);
  padding: 14px 16px;
  min-height: 88px;
}
.probe.ok { border-left-color: var(--ops-ok); }
.probe.bad { border-left-color: var(--ops-bad); }
.probe.prod { border-left-color: var(--ops-warn); }
.probe.dev { border-left-color: #2563eb; }
.probe-k { font-size: 12px; color: var(--ops-muted); letter-spacing: 0.04em; text-transform: uppercase; }
.probe-v { margin-top: 6px; font-size: 22px; font-weight: 700; color: var(--ops-ink); font-variant-numeric: tabular-nums; }
.probe-s { margin-top: 4px; font-size: 12px; color: var(--ops-muted); }
.block { margin-bottom: 16px; }
.panel { margin-bottom: 16px; border: 1px solid var(--ops-line); }
.panel-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.meta { font-size: 12px; color: var(--ops-muted); margin-bottom: 10px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.fault-actions, .toolbar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.st-ok { color: var(--ops-ok); font-weight: 600; }
.st-bad { color: var(--ops-bad); font-weight: 600; }
.st-unk { color: var(--ops-warn); }
.metrics {
  white-space: pre-wrap;
  font-size: 12px;
  max-height: 280px;
  overflow: auto;
  margin: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: #0b1220;
  color: #cbd5e1;
  padding: 12px;
}
@media (max-width: 1100px) {
  .probe-row { grid-template-columns: 1fr 1fr; }
}
</style>
