<template>
  <section>
    <div class="heading"><div><h3>已开通企业</h3><p>统一管理企业、成员账号与接入额度；选择企业查看成员和完整操作记录。</p></div><el-button v-if="userStore.hasPermission('service:admit')" type="primary" @click="$emit('onboard')">开通企业</el-button></div>
    <div class="filters"><el-input v-model="keyword" placeholder="搜索企业名称" clearable /><el-select v-model="status" placeholder="全部状态" clearable><el-option label="已启用" value="active" /><el-option label="已停用" value="disabled" /></el-select><el-button :loading="loading" @click="load">刷新</el-button></div>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-table v-loading="loading" :data="filtered" stripe>
      <template #empty><el-empty description="暂无符合条件的已开通企业" /></template>
      <el-table-column prop="name" label="企业名称" min-width="180" />
      <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status === 'active' ? '已启用' : '已停用' }}</el-tag></template></el-table-column>
      <el-table-column prop="member_count" label="成员数" width="90" />
      <el-table-column label="开通时间（北京时间）" min-width="180"><template #default="{ row }">{{ time(row.created_at) }}</template></el-table-column>
      <el-table-column label="管理" min-width="280"><template #default="{ row }">
        <el-button v-if="userStore.hasPermission('service:admit')" link type="primary" @click="inspect(row)">成员与记录</el-button>
        <el-button v-if="userStore.hasPermission('service:admit')" link @click="open('company', row)">编辑</el-button>
        <el-button v-if="userStore.hasPermission('service:admit')" link :disabled="row.status !== 'active'" @click="$emit('grant', row)">交付数据集</el-button>
        <el-button v-if="userStore.hasPermission('service:admit')" link type="danger" @click="removeCompany(row)">删除</el-button>
      </template></el-table-column>
    </el-table>
    <el-drawer v-model="drawer" :title="company?.name || '企业管理'" size="min(1100px, 96vw)" @closed="clearDrawer">
      <el-alert v-if="drawerError" :title="drawerError" type="error" :closable="false" />
      <el-tabs v-model="detailTab">
        <el-tab-pane label="企业成员" name="members">
          <div class="heading"><p>密码以加密摘要存储。可重置密码，账号名固定用于登录和历史追踪。</p><el-button v-if="userStore.hasPermission('service:admit')" :disabled="company?.status !== 'active'" @click="open('member')">添加成员</el-button></div>
          <el-table v-loading="detailLoading" :data="companyMembers" stripe>
            <el-table-column prop="username" label="登录账号" min-width="160" /><el-table-column prop="nickname" label="姓名 / 昵称" min-width="110" /><el-table-column prop="email" label="邮箱" min-width="160" /><el-table-column prop="phone" label="电话" min-width="130" />
            <el-table-column label="状态" width="90"><template #default="{ row }">{{ { active: '正常', disabled: '已停用', deleted: '已删除' }[row.status] || row.status }}</template></el-table-column>
            <el-table-column label="操作" min-width="250"><template #default="{ row }">
              <el-button v-if="userStore.hasPermission('service:admit') && row.status !== 'deleted'" link type="primary" @click="open('editMember', row)">编辑</el-button>
              <el-button v-if="userStore.hasPermission('service:admit') && row.status !== 'deleted'" link @click="open('password', row)">重置密码</el-button>
              <el-button v-if="userStore.hasPermission('service:records')" link type="primary" @click="memberRecords(row)">评测记录</el-button>
              <el-button v-if="userStore.hasPermission('service:admit') && row.status !== 'deleted'" link type="danger" @click="removeMember(row)">删除</el-button>
            </template></el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane v-if="userStore.hasPermission('service:records')" label="操作记录" name="records"><ServiceRecords v-if="drawer && company && detailTab === 'records'" ref="recordsRef" :tenant-id="company.id" :members="companyMembers" /></el-tab-pane>
        <el-tab-pane label="接入方与配额" name="clients"><p>选择接入方调整配额和价格，无需输入 ID。</p><el-table v-loading="detailLoading" :data="companyClients"><el-table-column prop="name" label="接入方" /><el-table-column prop="workspace_name" label="工作空间" /><el-table-column prop="daily_tokens" label="每日 Token 额度" /><el-table-column prop="monthly_tokens" label="每月 Token 额度" /><el-table-column label="状态"><template #default="{ row }">{{ row.active ? '有效' : '已撤销' }}</template></el-table-column><el-table-column label="操作"><template #default="{ row }"><el-button v-if="userStore.hasPermission('service:admit')" link type="primary" @click="$emit('quota', row)">调整额度</el-button></template></el-table-column></el-table></el-tab-pane>
      </el-tabs>
    </el-drawer>
    <el-dialog v-model="dialog" :title="titles[kind]" width="min(560px, 94vw)" append-to-body :close-on-click-modal="false" @closed="clearForm">
      <el-form label-position="top" @submit.prevent="save">
        <template v-if="kind === 'company'"><el-form-item label="企业名称（必填）"><el-input v-model="form.name" maxlength="120" /></el-form-item><el-form-item label="企业状态"><el-radio-group v-model="form.status"><el-radio value="active">启用</el-radio><el-radio value="disabled">停用</el-radio></el-radio-group></el-form-item><p>停用后成员将无法使用评测服务，API 密钥也会被拒绝。</p></template>
        <template v-else-if="kind === 'editMember'"><el-form-item label="登录账号"><el-input :model-value="selected.username" disabled /></el-form-item><el-form-item label="姓名 / 昵称"><el-input v-model="form.nickname" maxlength="50" /></el-form-item><el-form-item label="邮箱"><el-input v-model="form.email" maxlength="255" /></el-form-item><el-form-item label="电话"><el-input v-model="form.phone" maxlength="20" /></el-form-item><el-form-item label="账号状态"><el-radio-group v-model="form.status"><el-radio value="active">正常</el-radio><el-radio value="disabled">停用</el-radio></el-radio-group></el-form-item></template>
        <template v-else><el-form-item v-if="kind === 'member'" label="登录账号（必填）"><el-input v-model="form.username" placeholder="3–50 位字母、数字、下划线、点或短横线" maxlength="50" autocomplete="off" /></el-form-item><el-form-item label="密码（至少 12 字符，含字母和数字）"><el-input v-model="form.password" type="password" show-password autocomplete="new-password" maxlength="72" /><el-button v-if="userStore.hasPermission('service:admit')" link type="primary" @click="form.password = generatePassword()">生成随机密码</el-button></el-form-item><p>请在保存前妥善记录密码，关闭后无法查看。</p></template>
        <el-alert v-if="formError" :title="formError" type="error" :closable="false" />
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button v-if="userStore.hasPermission('service:admit')" type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { servicePortalApi as api } from '@/api'
import { useUserStore } from '@/stores/user'
import ServiceRecords from './ServiceRecords.vue'
const userStore = useUserStore()
defineEmits(['onboard', 'grant', 'quota'])
const companies = ref([]), keyword = ref(''), status = ref(''), loading = ref(false), error = ref('')
const drawer = ref(false), company = ref(null), companyMembers = ref([]), companyClients = ref([]), detailTab = ref('members'), recordsRef = ref(null), detailLoading = ref(false), drawerError = ref('')
const dialog = ref(false), kind = ref(''), form = ref({}), selected = ref(null), saving = ref(false), formError = ref('')
let generation = 0, detailGeneration = 0
const titles = { company: '编辑企业', member: '添加企业成员', editMember: '编辑成员资料', password: '重置成员密码' }
const filtered = computed(() => companies.value.filter(c => c.name.toLowerCase().includes(keyword.value.trim().toLowerCase()) && (!status.value || c.status === status.value)))
const time = value => new Date(value + 'Z').toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
const message = e => typeof e.response?.data?.detail === 'string' ? e.response.data.detail : e.message || '操作失败，请重试'
const generatePassword = () => { const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'; return 'Ev9!' + Array.from(crypto.getRandomValues(new Uint8Array(18)), n => chars[n % chars.length]).join('') }
async function load() {
  const run = ++generation
  loading.value = true; error.value = ''
  try { const result = await api.customers(); if (run === generation) companies.value = result.items }
  catch (e) { if (run === generation) error.value = message(e) }
  finally { if (run === generation) loading.value = false }
}
async function loadDetails() {
  if (!company.value) return
  const run = ++detailGeneration, id = company.value.id
  detailLoading.value = true; drawerError.value = ''
  try { const [m, c] = await Promise.all([api.customerMembers(id), api.customerClients(id)]); if (run === detailGeneration) { companyMembers.value = m.items; companyClients.value = c.items } }
  catch (e) { if (run === detailGeneration) drawerError.value = message(e) }
  finally { if (run === detailGeneration) detailLoading.value = false }
}
function inspect(row) { company.value = row; detailTab.value = 'members'; companyMembers.value = []; companyClients.value = []; drawer.value = true; loadDetails() }
function clearDrawer() { detailGeneration++; company.value = null; companyMembers.value = []; companyClients.value = [] }
function clearForm() { form.value = {}; formError.value = '' }
function open(type, row = null) { kind.value = type; selected.value = row; formError.value = ''; form.value = type === 'company' ? { name: row.name, status: row.status } : type === 'editMember' ? { nickname: row.nickname, email: row.email, phone: row.phone, status: row.status } : { username: '', password: '' }; dialog.value = true }
async function save() {
  if (saving.value) return
  saving.value = true; formError.value = ''
  try {
    const data = { ...form.value }, tid = company.value?.id
    if (kind.value === 'company') { if (!data.name.trim()) throw new Error('请输入企业名称'); await api.updateCustomer(selected.value.id, data) }
    else if (kind.value === 'editMember') { if (data.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) throw new Error('请输入有效邮箱'); await api.updateCustomerMember(tid, selected.value.id, data) }
    else { if (data.password.length < 12 || !/[a-zA-Z]/.test(data.password) || !/\d/.test(data.password)) throw new Error('密码至少 12 字符，且包含字母和数字'); if (kind.value === 'member') { if (!/^[a-zA-Z0-9_.-]{3,50}$/.test(data.username)) throw new Error('请填写有效登录账号'); await api.addCustomerMember(tid, data) } else await api.resetCustomerPassword(tid, selected.value.id, { password: data.password }) }
    dialog.value = false; clearForm(); ElMessage.success('已保存'); await load(); if (drawer.value) await loadDetails()
  } catch (e) { formError.value = message(e) } finally { saving.value = false }
}
async function removeCompany(row) {
  try { await ElMessageBox.confirm(`删除企业“${row.name}”后，成员及 API 将无法使用评测服务。历史记录和计量数据保留。`, '删除企业', { type: 'warning', confirmButtonText: '删除企业' }) } catch { return }
  try { await api.deleteCustomer(row.id); ElMessage.success('企业已删除'); await load() } catch (e) { ElMessage.error(message(e)) }
}
async function removeMember(row) {
  try { await ElMessageBox.confirm(`删除成员“${row.username}”后将禁止登录，其创建的 API 密钥也将失效，历史评测记录保留。`, '删除成员', { type: 'warning', confirmButtonText: '删除成员' }) } catch { return }
  try { await api.deleteCustomerMember(company.value.id, row.id); ElMessage.success('成员已删除'); await Promise.all([loadDetails(), load()]) } catch (e) { ElMessage.error(message(e)) }
}
async function memberRecords(row) { detailTab.value = 'records'; await nextTick(); recordsRef.value?.filterMember(row.id) }
onMounted(load)
onUnmounted(() => { generation++; detailGeneration++ })
defineExpose({ load, loadDetails })
</script>

<style scoped>
.heading { display: flex; justify-content: space-between; gap: 18px; align-items: center; margin: 18px 0; } h3 { margin: 0 0 8px; } p { color: var(--text-secondary); font-size: 13px; line-height: 1.7; }
.filters { display: flex; gap: 12px; flex-wrap: wrap; margin: 20px 0; } .filters .el-input { width: 260px; } .filters .el-select { width: 160px; }
@media (max-width: 600px) { .heading { flex-direction: column; align-items: flex-start; } }
</style>
