<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">被测模型</h2>
        <p class="page-desc">注册、版本、接入映射、调用 ACL 与周期健康探测</p>
      </div>
      <el-button v-if="userStore.hasPermission('model:create')" type="primary" @click="openCreate">注册模型</el-button>
    </div>
    <el-card>
      <div class="toolbar">
        <el-input v-model="search" placeholder="搜索模型" clearable style="width: 220px" />
        <el-select v-model="source" placeholder="来源" clearable style="width: 140px">
          <el-option label="外部企业" value="external" />
          <el-option label="内部" value="internal" />
        </el-select>
      </div>
      <el-table v-loading="loading" :data="items" stripe>
        <template #empty>
          <EmptyState type="model" action-text="注册模型" :show-action="userStore.hasPermission('model:create')" @action="openCreate" />
        </template>
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="model_source" label="来源" width="90" />
        <el-table-column prop="access_mode" label="接入" width="130" />
        <el-table-column prop="current_version" label="版本" width="80" />
        <el-table-column prop="health_status" label="健康" width="90">
          <template #default="{ row }">
            <StatusBadge
              :phase="row.health_status === 'ok' || row.health_status === 'healthy' ? 'completed' : row.health_status === 'fail' || row.health_status === 'unhealthy' ? 'failed' : 'idle'"
              :text="row.health_status || '未探测'"
            />
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column label="连接" width="110">
          <template #default="{ row }">
            <span :class="(row.api_url || '').trim() ? 'ok' : 'warn'">{{ (row.api_url || '').trim() ? '已配置' : '未配置' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <div class="op-btns">
              <el-button v-if="userStore.hasPermission('model:view')" link type="primary" size="small" @click="openDetail(row)">详情</el-button>
              <el-button v-if="userStore.hasPermission('model:view')" link type="primary" size="small" @click="checkHealth(row)">探测</el-button>
              <el-button v-if="userStore.hasPermission('model:invoke')" link type="primary" size="small" @click="openInvoke(row)">试调用</el-button>
              <el-button v-if="userStore.hasPermission('model:edit')" link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
              <el-button v-if="userStore.hasPermission('model:delete')" link type="danger" size="small" @click="remove(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-if="total > 0"
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @current-change="loadData"
        @size-change="() => { page = 1; loadData() }"
      />
    </el-card>

    <el-dialog v-model="showForm" :title="form.id ? '编辑模型' : '注册模型'" width="720px">
      <el-tabs>
        <el-tab-pane label="基础">
          <el-form :model="form" label-width="120px">
            <el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item>
            <el-form-item label="来源">
              <el-select v-model="form.model_source">
                <el-option label="外部企业" value="external" />
                <el-option label="内部" value="internal" />
              </el-select>
            </el-form-item>
            <el-form-item label="接入模式">
              <el-select v-model="form.access_mode">
                <el-option label="在线评测" value="online" />
                <el-option label="远程加密访问" value="remote_encrypted" />
              </el-select>
            </el-form-item>
            <el-form-item label="模态"><el-input v-model="form.support_modal" placeholder="text / multimodal" /></el-form-item>
            <el-form-item label="场景白名单">
              <el-select v-model="form.scene_white_list" multiple filterable allow-create default-first-option style="width: 100%" placeholder="空表示不限制">
                <el-option v-for="s in scenes" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
            <el-form-item label="并发上限"><el-input-number v-model="form.parallel_limit" :min="1" :max="64" /></el-form-item>
            <el-form-item label="描述"><el-input v-model="form.description" type="textarea" rows="2" /></el-form-item>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="接入">
          <el-form :model="form" label-width="120px">
            <el-form-item label="接口地址">
              <el-input v-model="form.api_url" placeholder="必填：真实推理服务 URL；留空将无法正式调用" />
              <div class="field-hint">未配置 api_url 时无法探测或试调用。</div>
            </el-form-item>
            <el-form-item label="模型名"><el-input v-model="form.served_model_name" /></el-form-item>
            <el-form-item label="API Key"><el-input v-model="form.api_key" type="password" show-password placeholder="不修改请留空" /></el-form-item>
            <el-form-item label="通道">
              <el-select v-model="form.channel_type">
                <el-option label="HTTPS" value="https" />
                <el-option label="mTLS 远程加密" value="mtls" />
                <el-option label="VPN" value="vpn" />
                <el-option label="网关" value="gateway" />
                <el-option label="明文（仅联调）" value="plain" />
              </el-select>
              <div class="field-hint">HTTPS 按证书校验直接调用。mTLS 需要服务器已配置客户端证书和私钥，否则调用会失败。VPN 和网关不会由平台自行建隧道，只表示地址已经走企业网络或网关，请求仍按 HTTPS 校验。明文关闭证书校验，仅非生产联调可用。</div>
            </el-form-item>
            <el-form-item label="超时/重试">
              <el-input-number v-model="form.timeout" :min="5" /> 秒，重试
              <el-input-number v-model="form.retry_count" :min="0" :max="5" />
            </el-form-item>
            <el-form-item label="请求模板">
              <el-input v-model="form.request_template" type="textarea" rows="4" placeholder='可选 JSON，支持 {{prompt}} {{model}}' />
            </el-form-item>
            <el-form-item label="响应映射">
              <el-input v-model="form.response_mapping" type="textarea" rows="2" placeholder='{"output":"choices.0.message.content","tokens":"usage.total_tokens"}' />
            </el-form-item>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="元信息">
          <el-form :model="form" label-width="120px">
            <el-form-item label="架构"><el-input v-model="form.architecture" /></el-form-item>
            <el-form-item label="参数规模"><el-input v-model="form.parameter_scale" /></el-form-item>
            <el-form-item label="上下文长度"><el-input-number v-model="form.context_length" :min="512" /></el-form-item>
            <el-form-item label="训练数据"><el-input v-model="form.train_data_desc" type="textarea" rows="2" /></el-form-item>
            <el-form-item label="微调方式"><el-input v-model="form.finetune_method" /></el-form-item>
            <el-form-item label="推理框架"><el-input v-model="form.infer_framework" /></el-form-item>
            <el-form-item label="硬件"><el-input v-model="form.hardware" /></el-form-item>
            <el-form-item label="企业/联系人">
              <el-input v-model="form.company_name" placeholder="企业" />
              <el-input v-model="form.contact_name" placeholder="对接人" style="margin-top: 8px" />
            </el-form-item>
            <el-form-item v-if="form.model_source === 'internal'" label="内部来源">
              <el-select v-model="form.source_type">
                <el-option label="开源" value="open_source" />
                <el-option label="自研" value="self_dev" />
                <el-option label="微调" value="fine_tune" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="form.model_source === 'internal'" label="基座/集群">
              <el-input v-model="form.base_model" placeholder="base_model" />
              <el-input v-model="form.deploy_cluster" placeholder="deploy_cluster" style="margin-top: 8px" />
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="showDetail" title="模型详情" size="520px">
      <template v-if="detail.id">
        <p>健康 {{ detail.health_status }} · 状态 {{ detail.status }} · 占用任务 {{ detail.in_use || 0 }}</p>
        <h4>版本</h4>
        <el-form inline>
          <el-form-item><el-input v-model="newVer.version_code" placeholder="V2.0" style="width: 100px" /></el-form-item>
          <el-form-item><el-button v-if="userStore.hasPermission('model:edit')" type="primary" @click="addVersion">新增版本</el-button></el-form-item>
        </el-form>
        <el-table :data="detail.versions || []" size="small">
          <el-table-column prop="version_code" label="版本" />
          <el-table-column prop="version_desc" label="说明" />
          <el-table-column label="" width="80">
            <template #default="{ row }">
              <el-button v-if="row.id !== detail.current_version_id && userStore.hasPermission('model:edit')" link type="primary" size="small" @click="activate(row)">启用</el-button>
            </template>
          </el-table-column>
        </el-table>
        <h4>调用 ACL</h4>
        <el-form inline>
          <el-form-item><el-input-number v-model="newAcl.principal_id" :min="1" placeholder="用户ID" /></el-form-item>
          <el-form-item><el-button v-if="userStore.hasPermission('model:edit')" @click="addAcl">允许调用</el-button></el-form-item>
        </el-form>
        <el-table :data="detail.acls || []" size="small">
          <el-table-column prop="principal_type" label="主体" width="80" />
          <el-table-column prop="principal_id" label="ID" width="70" />
          <el-table-column prop="allow" label="允许" width="70">
            <template #default="{ row }">{{ row.allow ? '是' : '否' }}</template>
          </el-table-column>
          <el-table-column label="" width="70">
            <template #default="{ row }">
              <el-button v-if="userStore.hasPermission('model:edit')" link type="danger" size="small" @click="removeAcl(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <h4>健康探测</h4>
        <el-table :data="detail.health_samples || []" size="small">
          <el-table-column prop="status" label="状态" width="90" />
          <el-table-column prop="latency_ms" label="时延" width="80" />
          <el-table-column prop="detail" label="说明" show-overflow-tooltip />
        </el-table>
        <h4>调用日志</h4>
        <el-table :data="detail.logs || []" size="small">
          <el-table-column prop="call_status" label="结果" width="80" />
          <el-table-column prop="latency_ms" label="时延" width="80" />
          <el-table-column prop="token_usage" label="Token" width="80" />
          <el-table-column prop="error_message" label="错误" show-overflow-tooltip />
        </el-table>
      </template>
    </el-drawer>

    <el-dialog v-model="showInvoke" title="试调用" width="640px">
      <el-input v-model="invokePrompt" type="textarea" rows="4" placeholder="输入提示词" />
      <el-button type="primary" style="margin-top: 12px" :loading="invoking" @click="doInvoke">发送</el-button>
      <pre v-if="invokeResult" class="result">{{ invokeResult }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { modelsApi } from '@/api'
import { useUserStore } from '@/stores/user'
import EmptyState from '@/components/EmptyState.vue'
import StatusBadge from '@/components/StatusBadge.vue'

const userStore = useUserStore()
const scenes = ['qa', '智能对话', '表格分析', '文本写作', 'RAG', '代码应用']
const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const search = ref('')
const source = ref('')
const showForm = ref(false)
const submitting = ref(false)
const form = ref({})
const showInvoke = ref(false)
const invokePrompt = ref('你好')
const invokeResult = ref('')
const invoking = ref(false)
const invokeId = ref(null)
const showDetail = ref(false)
const detail = ref({})
const newVer = ref({ version_code: '', version_desc: '' })
const newAcl = ref({ principal_id: 1, principal_type: 'user', allow: true })

function emptyForm() {
  return {
    name: '', model_source: 'external', access_mode: 'online', api_url: '',
    served_model_name: '', api_key: '', channel_type: 'https', description: '',
    support_modal: 'text', scene_white_list: [], parallel_limit: 4,
    timeout: 60, retry_count: 1, request_template: '', response_mapping: '',
    architecture: '', parameter_scale: '', context_length: 8192,
    train_data_desc: '', finetune_method: '', infer_framework: '', hardware: '',
    company_name: '', contact_name: '', source_type: '', base_model: '', deploy_cluster: ''
  }
}

async function loadData() {
  loading.value = true
  try {
    const res = await modelsApi.list({
      search: search.value || undefined,
      model_source: source.value || undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    items.value = res.items || []
    total.value = res.total ?? items.value.length
  } finally {
    loading.value = false
  }
}

function openCreate() { form.value = emptyForm(); showForm.value = true }
function openEdit(row) { form.value = { ...emptyForm(), ...row, api_key: '', scene_white_list: row.scene_white_list || [] }; showForm.value = true }

async function openDetail(row) {
  detail.value = await modelsApi.get(row.id)
  showDetail.value = true
}

async function submit() {
  submitting.value = true
  try {
    if (form.value.id) await modelsApi.update(form.value.id, form.value)
    else await modelsApi.create(form.value)
    ElMessage.success('已保存')
    showForm.value = false
    loadData()
  } finally {
    submitting.value = false
  }
}

async function checkHealth(row) {
  const res = await modelsApi.health(row.id)
  ElMessage[res.ok ? 'success' : 'warning'](res.detail || res.status)
  loadData()
}

function openInvoke(row) {
  invokeId.value = row.id
  invokeResult.value = ''
  showInvoke.value = true
}

async function doInvoke() {
  invoking.value = true
  try {
    const res = await modelsApi.invoke(invokeId.value, { prompt: invokePrompt.value })
    invokeResult.value = res.output
  } finally {
    invoking.value = false
  }
}

async function addVersion() {
  if (!newVer.value.version_code.trim()) return
  await modelsApi.createVersion(detail.value.id, newVer.value)
  newVer.value = { version_code: '', version_desc: '' }
  detail.value = await modelsApi.get(detail.value.id)
  loadData()
}

async function activate(row) {
  await modelsApi.activateVersion(detail.value.id, row.id)
  detail.value = await modelsApi.get(detail.value.id)
  loadData()
}

async function addAcl() {
  await modelsApi.addAcl(detail.value.id, newAcl.value)
  detail.value = await modelsApi.get(detail.value.id)
}

async function removeAcl(row) {
  await modelsApi.deleteAcl(detail.value.id, row.id)
  detail.value = await modelsApi.get(detail.value.id)
}

async function remove(row) {
  await ElMessageBox.confirm(`将逻辑删除模型「${row.name}」。历史任务占用时配置仍保留。`, '确认')
  await modelsApi.delete(row.id)
  loadData()
}

let timer
watch([search, source], () => {
  clearTimeout(timer)
  timer = setTimeout(() => { page.value = 1; loadData() }, 250)
})
onMounted(loadData)
</script>

<style scoped>
.result { margin-top: 12px; white-space: pre-wrap; background: var(--bg-page); padding: 12px; border-radius: 8px; }
h4 { margin: 16px 0 8px; }
.pagination { margin-top: 16px; justify-content: flex-end; }
.field-hint { margin-top: 4px; font-size: 12px; color: var(--el-text-color-secondary); }
.ok { color: var(--el-color-success); font-size: 12px; }
.warn { color: var(--el-color-warning); font-size: 12px; }
</style>
