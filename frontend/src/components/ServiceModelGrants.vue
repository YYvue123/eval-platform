<template>
  <section>
    <div class="heading"><div><h3>平台模型授权</h3><p>选择平台模型及冻结版本交付给当前企业，客户即可在“关联已有版本”中使用。</p></div><el-button :loading="loading" @click="load">刷新</el-button></div>
    <el-alert title="按所选版本交付独立快照，不自动同步平台后续配置。上游凭据不会在客户页面展示。" type="info" :closable="false" />
    <el-form v-if="userStore.hasPermission('service:admit')" label-position="top" class="grant-form" @submit.prevent="grant">
      <el-form-item label="平台模型"><el-select v-model="modelId" filterable clearable placeholder="选择可授权的平台模型" :loading="loading" :disabled="disabled" @change="versionIds = []"><el-option v-for="m in options" :key="m.id" :value="m.id" :label="m.name" /></el-select></el-form-item>
      <el-form-item label="冻结模型版本"><el-select v-model="versionIds" multiple filterable :multiple-limit="20" placeholder="选择允许企业使用的版本" :disabled="disabled || !modelId"><el-option v-for="v in versions" :key="v.id" :value="v.id" :label="v.version" /></el-select></el-form-item>
      <el-button type="primary" :loading="saving" :disabled="disabled || !modelId || !versionIds.length || loading" @click="grant">授权所选版本</el-button>
      <p v-if="!loading && !options.length">暂无可授权模型，请在被测模型中准备可用版本及冻结接口配置。</p>
      <p v-if="disabled">企业已停用，请先启用企业再新增授权。</p>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-table v-loading="loading" :data="items" stripe>
      <template #empty><el-empty description="尚未向该企业授权平台模型" /></template>
      <el-table-column prop="name" label="平台模型" min-width="180" />
      <el-table-column prop="version" label="冻结版本" min-width="110" />
      <el-table-column label="授权状态" width="100"><template #default="{ row }"><el-tag :type="row.active ? 'success' : 'info'">{{ row.active ? '已授权' : '已撤销' }}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="100"><template #default="{ row }"><el-button v-if="userStore.hasPermission('service:admit') && row.active" link type="danger" :disabled="revoking === row.id" @click="revoke(row)">撤销授权</el-button></template></el-table-column>
    </el-table>
    <p>授权后客户仍需将模型版本关联到模型服务并配置稳定路由。撤销后该版本不能用于新评测，历史记录保留；不要把撤销当作取消已运行任务。</p>
  </section>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { servicePortalApi as api } from '@/api'
import { useUserStore } from '@/stores/user'
const props = defineProps({ tenantId: { type: Number, required: true }, disabled: Boolean })
const userStore = useUserStore()
const options = ref([]), items = ref([]), modelId = ref(null), versionIds = ref([]), loading = ref(false), saving = ref(false), revoking = ref(null), error = ref('')
let generation = 0
const versions = computed(() => options.value.find(m => m.id === modelId.value)?.versions || [])
const message = e => typeof e.response?.data?.detail === 'string' ? e.response.data.detail : e.message || '操作失败，请重试'
async function load() {
  const run = ++generation, tid = props.tenantId
  loading.value = true; error.value = ''
  try { const [o, g] = await Promise.all([api.modelGrantOptions(), api.modelGrants(tid)]); if (run === generation) { options.value = o.items; items.value = g.items } }
  catch (e) { if (run === generation) error.value = message(e) }
  finally { if (run === generation) loading.value = false }
}
async function grant() {
  if (saving.value || !modelId.value || !versionIds.value.length) return
  const tid = props.tenantId
  saving.value = true; error.value = ''
  try { await api.grantModels(tid, { model_id: modelId.value, version_ids: versionIds.value }); if (props.tenantId === tid) { ElMessage.success('已授权，客户可在关联已有版本中选择'); versionIds.value = []; await load() } }
  catch (e) { if (props.tenantId === tid) error.value = message(e) }
  finally { saving.value = false }
}
async function revoke(row) {
  try { await ElMessageBox.confirm(`撤销“${row.name} / ${row.version}”后，客户不能再用该版本提交新评测。历史记录保留，已运行任务需单独核对。`, '撤销模型授权', { type: 'warning', confirmButtonText: '撤销授权' }) } catch { return }
  const tid = props.tenantId
  revoking.value = row.id; error.value = ''
  try { await api.revokeModelGrant(tid, row.id); if (props.tenantId === tid) { ElMessage.success('已撤销授权'); await load() } }
  catch (e) { if (props.tenantId === tid) error.value = message(e) }
  finally { revoking.value = null }
}
watch(() => props.tenantId, () => { modelId.value = null; versionIds.value = []; items.value = []; load() }, { immediate: true })
onUnmounted(() => generation++)
</script>

<style scoped>
.heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin: 18px 0; } h3 { margin: 0 0 8px; } p { font-size: 13px; color: var(--text-secondary); line-height: 1.7; }
.grant-form { margin: 22px 0; max-width: 650px; } .el-select { width: 100%; }
</style>
