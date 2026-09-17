<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">工具底座</h2>
        <p class="page-desc">按 V0.6.1 注册 Manifest；Skill 链式 $ref、MCP JSON-RPC、进程内注册发现。</p>
      </div>
      <el-button v-if="userStore.hasPermission('resource:invoke')" @click="showBatch = true">冻结批次</el-button>
      <el-button v-if="userStore.hasPermission('resource:create')" type="primary" @click="showReg = true">注册 Manifest</el-button>
    </div>
    <el-card>
      <div class="toolbar">
        <el-select v-model="resourceType" placeholder="类型" clearable style="width: 160px">
          <el-option label="Tool" value="tool" />
          <el-option label="DataSource" value="datasource" />
          <el-option label="Model" value="model" />
          <el-option label="Skill" value="skill" />
          <el-option label="MCP" value="mcp" />
          <el-option label="Agent" value="agent" />
        </el-select>
      </div>
      <el-table v-loading="loading" :data="items" stripe>
        <el-table-column prop="resource_id" label="资源 ID" min-width="180" />
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="resource_type" label="类型" width="110" />
        <el-table-column prop="version" label="版本" width="90" />
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column prop="call_count" label="调用" width="80" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button v-if="['tool','skill','mcp'].includes(row.resource_type) && userStore.hasPermission('resource:invoke')" link type="primary" size="small" @click="tryInvoke(row)">试调用</el-button>
            <el-button v-if="userStore.hasPermission('resource:view')" link type="primary" size="small" @click="health(row)">健康</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showBatch" title="冻结批量快照" width="480px">
      <el-form label-width="100px">
        <el-form-item label="数据集 ID"><el-input-number v-model="batchForm.dataset_id" :min="1" /></el-form-item>
        <el-form-item label="分片大小"><el-input-number v-model="batchForm.shard_size" :min="1" :max="500" /></el-form-item>
      </el-form>
      <p v-if="batchInfo">batch={{ batchInfo.batch_id }} snapshot={{ batchInfo.snapshot_id }} 条数={{ batchInfo.item_count }}</p>
      <template #footer>
        <el-button @click="showBatch = false">关闭</el-button>
        <el-button type="primary" @click="runBatch">创建批次</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="showReg" title="注册 Manifest" width="720px">
      <el-input v-model="manifestText" type="textarea" rows="16" placeholder="粘贴 manifest.json" />
      <template #footer>
        <el-button @click="showReg = false">取消</el-button>
        <el-button type="primary" @click="register">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { resourcesApi, batchApi } from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const loading = ref(false)
const items = ref([])
const resourceType = ref('')
const showReg = ref(false)
const manifestText = ref('')
const showBatch = ref(false)
const batchForm = ref({ dataset_id: 1, shard_size: 50 })
const batchInfo = ref(null)

async function loadData() {
  loading.value = true
  try {
    const res = await resourcesApi.list({ resource_type: resourceType.value, page_size: 100 })
    items.value = res.items || []
  } finally {
    loading.value = false
  }
}

async function register() {
  const manifest = JSON.parse(manifestText.value)
  await resourcesApi.register(manifest)
  ElMessage.success('注册成功')
  showReg.value = false
  loadData()
}

async function tryInvoke(row) {
  let body = { prediction: '北京', reference: '北京' }
  if (row.resource_type === 'mcp') {
    body = { jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'builtin/exact_match', arguments: { prediction: '北京', reference: '北京' } } }
  }
  const res = await resourcesApi.invoke({ resource_id: row.resource_id, body })
  ElMessage.success(`status=${res.header?.status || 'ok'}`)
}

async function health(row) {
  const res = await resourcesApi.health(row.resource_id)
  ElMessage[res.ok ? 'success' : 'warning'](res.detail || res.status)
}

async function runBatch() {
  batchInfo.value = await batchApi.run(batchForm.value)
  ElMessage.success('已冻结快照')
}

watch(resourceType, loadData)
onMounted(loadData)
</script>
