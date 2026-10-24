<template>
  <section>
    <div class="section-heading"><div><h3>评测操作记录</h3><p>查看成员提交、执行、取消、下载报告及服务管理操作。API 调用归属密钥创建成员，切换至 API 访问记录可查看请求路径和响应状态。</p></div></div>
    <el-radio-group v-model="source" @change="search"><el-radio-button value="operations">成员操作</el-radio-button><el-radio-button value="gateway">API 访问记录</el-radio-button></el-radio-group>
    <el-form inline class="record-filters" @submit.prevent="search">
      <el-form-item label="成员"><el-select v-model="filters.member_id" filterable clearable placeholder="全部成员" @change="search"><el-option v-for="m in members" :key="m.id" :value="m.id" :label="`${m.username}${m.status === 'deleted' ? '（已删除）' : ''}`" /></el-select></el-form-item>
      <el-form-item v-if="source === 'operations'" label="操作"><el-select v-model="filters.action" clearable filterable placeholder="全部操作" @change="search"><el-option v-for="(label, value) in actions" :key="value" :value="value" :label="label" /></el-select></el-form-item>
      <el-form-item label="时间"><el-date-picker v-model="dates" type="datetimerange" start-placeholder="开始时间" end-placeholder="结束时间" @change="search" /></el-form-item>
      <el-form-item><el-button :loading="loading" @click="search">查询</el-button><el-button @click="reset">重置</el-button></el-form-item>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-table v-loading="loading" :data="items" stripe>
      <template #empty><el-empty description="当前条件下暂无操作记录" /></template>
      <el-table-column label="时间（北京时间）" min-width="170"><template #default="{ row }">{{ time(row.created_at) }}</template></el-table-column>
      <el-table-column prop="username" label="操作成员" min-width="140" />
      <el-table-column label="模块" width="100"><template #default="{ row }">{{ row.resource === 'gateway' ? 'API 网关' : row.resource === 'task' ? '评测任务' : '评测服务' }}</template></el-table-column>
      <el-table-column label="操作" min-width="140"><template #default="{ row }">{{ actions[row.action] || row.action }}</template></el-table-column>
      <el-table-column prop="target_id" label="关联对象 ID" width="110" />
      <el-table-column label="详情" min-width="220" show-overflow-tooltip><template #default="{ row }">{{ detailText(row.detail) }}</template></el-table-column>
      <el-table-column label="查看" width="90"><template #default="{ row }"><el-button v-if="userStore.hasPermission('service:records')" link type="primary" @click="detail = row">详情</el-button></template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="total, prev, pager, next" @current-change="load" />
    <el-dialog :model-value="!!detail" title="操作详情" width="min(660px, 94vw)" append-to-body @close="detail = null">
      <el-descriptions v-if="detail" :column="1" border><el-descriptions-item label="操作成员">{{ detail.username }}</el-descriptions-item><el-descriptions-item label="操作时间">{{ time(detail.created_at) }}</el-descriptions-item><el-descriptions-item label="操作">{{ actions[detail.action] || detail.action }}</el-descriptions-item><el-descriptions-item label="关联对象">{{ detail.resource === 'gateway' ? '接入方' : detail.resource === 'task' ? '评测任务' : '评测服务对象' }} #{{ detail.target_id || '—' }}</el-descriptions-item></el-descriptions><pre>{{ detailText(detail?.detail) || '无附加信息' }}</pre>
    </el-dialog>
  </section>
</template>

<script setup>
import { onUnmounted, ref, watch } from 'vue'
import { servicePortalApi as api } from '@/api'
import { useUserStore } from '@/stores/user'
const props = defineProps({ tenantId: { type: Number, default: null }, members: { type: Array, default: () => [] } })
const userStore = useUserStore()
const items = ref([]), total = ref(0), page = ref(1), dates = ref(null), loading = ref(false), error = ref(''), detail = ref(null)
const source = ref('operations')
const filters = ref({ member_id: null, action: '' })
let generation = 0
const actions = { model_grant: '授权平台模型', model_revoke: '撤销模型授权', submit: '提交评测', rejected: '评测被拒绝', start: '确认执行', cancel: '取消评测', report_download: '下载报告', create: '创建任务', update: '更新任务', run: '执行任务', stop: '停止任务', retry: '重试任务', delete: '删除任务', workspace_create: '创建工作空间', customer_create: '开通企业', customer_update: '编辑企业', customer_delete: '删除企业', member_create: '添加成员', member_update: '编辑成员', member_delete: '删除成员', member_password: '重置密码', client_create: '创建接入方', client_revoke: '撤销密钥', quota: '调整配额', asset_grant: '交付数据集', route_register: '注册模型服务', version_register: '关联版本', endpoint_register: '注册模型接口', traffic: '调整灰度路由', rollback: '回滚版本' }
function detailText(value) {
  if (!value) return ''
  try {
    const data = JSON.parse(value)
    const labels = { client_name: '接入方', request_path: '请求路径', http_status: 'HTTP 状态', title: '评测标题', task_id: '任务 ID', mode: '配置方式', stable_id: '稳定版本 ID', candidate_id: '灰度版本 ID', gray_percent: '灰度比例（%）', daily_tokens: '每日 Token 额度', monthly_tokens: '每月 Token 额度', requests_per_minute: '每分钟请求数', price_fen_per_1k: '每千 Token 单价（分）' }
    return Object.entries(data).map(([key, val]) => `${labels[key] || key}：${key === 'mode' ? (val === 'expert' ? '专家模式' : '自动化模式') : val ?? '未配置'}`).join('；')
  } catch { return value }
}
const time = value => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '—'
async function load() {
  const run = ++generation
  loading.value = true; error.value = ''
  try {
    const result = await api.records({ source: source.value, tenant_id: props.tenantId || undefined, member_id: filters.value.member_id || undefined, action: filters.value.action || undefined, start: dates.value?.[0]?.toISOString(), end: dates.value?.[1]?.toISOString(), page: page.value })
    if (run !== generation) return
    items.value = result.items; total.value = result.total
  } catch (e) { if (run === generation) { items.value = []; total.value = 0; error.value = typeof e.response?.data?.detail === 'string' ? e.response.data.detail : '操作记录加载失败，请重试' } }
  finally { if (run === generation) loading.value = false }
}
function search() { page.value = 1; load() }
function reset() { filters.value = { member_id: null, action: '' }; dates.value = null; search() }
function filterMember(id) { filters.value.member_id = id; search() }
watch(() => props.tenantId, reset, { immediate: true })
onUnmounted(() => generation++)
defineExpose({ filterMember })
</script>

<style scoped>
h3 { margin-bottom: 8px; } p { font-size: 13px; color: var(--text-secondary); line-height: 1.7; }
.record-filters { margin: 20px 0; } .el-select { width: 180px; } .el-pagination { justify-content: flex-end; margin-top: 20px; } pre { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; }
@media (max-width: 700px) {
  .record-filters :deep(.el-form-item) { display: flex; width: 100%; margin-right: 0; }
  .record-filters :deep(.el-form-item__content) { min-width: 0; flex: 1; }
  .record-filters :deep(.el-date-editor) { width: 100%; min-width: 0; }
  .record-filters :deep(.el-range-input) { min-width: 0; }
  .el-select { width: 100%; }
}
</style>
