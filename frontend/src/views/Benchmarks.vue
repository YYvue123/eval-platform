<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">基准套件</h2>
        <p class="page-desc">文本/媒体/MUT/行业金标与 readiness 门禁；媒体禁止字符串冒充；代码禁宿主执行；MUT 禁平台管理工具。</p>
      </div>
    </div>
    <el-card>
      <div class="toolbar">
        <el-radio-group v-model="category" @change="loadData">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="text">文本</el-radio-button>
          <el-radio-button value="industry">行业</el-radio-button>
          <el-radio-button value="media">媒体</el-radio-button>
          <el-radio-button value="mut">MUT</el-radio-button>
        </el-radio-group>
        <el-select v-model="readiness" clearable placeholder="readiness" style="width: 140px; margin-left: 12px" @change="loadData">
          <el-option label="ready" value="ready" />
          <el-option label="draft" value="draft" />
          <el-option label="blocked" value="blocked" />
        </el-select>
      </div>
      <el-table v-loading="loading" :data="items" stripe>
        <el-table-column prop="code" label="编码" min-width="150" />
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="category" label="类" width="90" />
        <el-table-column prop="input_modality" label="模态" width="90" />
        <el-table-column prop="readiness" label="就绪" width="90">
          <template #default="{ row }">
            <el-tag :type="row.readiness === 'ready' ? 'success' : row.readiness === 'blocked' ? 'danger' : 'info'" size="small">{{ row.readiness }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金标包" width="80">
          <template #default="{ row }">{{ row.has_pack ? '有' : '-' }}</template>
        </el-table-column>
        <el-table-column label="指标" min-width="180">
          <template #default="{ row }">
            <span v-for="m in row.metrics || []" :key="m.code" class="metric">
              {{ m.code }}<em v-if="!m.observable">(n/o)</em>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="阻塞" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ (row.blockers || []).join('；') || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button v-if="userStore.hasPermission('task:edit') && row.readiness !== 'ready'" link type="primary" size="small" @click="markReady(row)">标 ready</el-button>
            <el-button link type="primary" size="small" @click="showDetail(row)">详情</el-button>
            <el-button v-if="row.has_pack" link type="primary" size="small" @click="showPack(row)">样本</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="sim-card">
      <template #header>轻量模拟器</template>
      <div class="toolbar">
        <el-select v-model="simCode" placeholder="模拟器" style="width: 220px">
          <el-option v-for="s in simulators" :key="s.code" :label="s.name" :value="s.code" />
        </el-select>
        <el-select v-model="simSuite" placeholder="套件" style="width: 200px; margin-left: 8px">
          <el-option v-for="c in packSuites" :key="c" :label="c" :value="c" />
        </el-select>
        <el-button type="primary" style="margin-left: 8px" :loading="simLoading" @click="runSim">试跑</el-button>
      </div>
      <pre v-if="simResult" class="schema">{{ JSON.stringify(simResult, null, 2) }}</pre>
    </el-card>

    <el-drawer v-model="drawer" title="套件详情" size="520px">
      <template v-if="current">
        <p>模板 {{ current.template_code }} · oracle {{ current.oracle_type }} · license {{ current.license }}</p>
        <p>MUT 隔离 {{ current.mut_isolated ? '是' : '否' }} · 宿主执行代码 {{ current.code_host_exec ? '是' : '否' }}</p>
        <h4>门禁</h4>
        <ul>
          <li v-for="b in current.blockers || []" :key="b">{{ b }}</li>
          <li v-if="!(current.blockers || []).length">无 blockers</li>
        </ul>
        <h4>警告</h4>
        <ul>
          <li v-for="w in current.warnings || []" :key="w">{{ w }}</li>
          <li v-if="!(current.warnings || []).length">无</li>
        </ul>
        <h4>Input Schema</h4>
        <pre class="schema">{{ JSON.stringify(current.input_schema || {}, null, 2) }}</pre>
      </template>
    </el-drawer>

    <el-drawer v-model="packDrawer" title="金标样本" size="560px">
      <template v-if="packDetail">
        <p>版本 {{ packDetail.version }} · 样本数 {{ packDetail.sample_count }} · 校准 {{ packDetail.calibration_ok ? '已接受' : '待定' }}</p>
        <pre class="schema">{{ JSON.stringify(packDetail.samples || [], null, 2) }}</pre>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { benchmarksApi } from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const loading = ref(false)
const items = ref([])
const category = ref('')
const readiness = ref('')
const drawer = ref(false)
const current = ref(null)
const packDrawer = ref(false)
const packDetail = ref(null)
const simulators = ref([])
const simCode = ref('sim.table_calc')
const simSuite = ref('bench.table')
const simLoading = ref(false)
const simResult = ref(null)

const packSuites = computed(() => items.value.filter((i) => i.has_pack).map((i) => i.code))

async function loadData() {
  loading.value = true
  try {
    const res = await benchmarksApi.list({
      category: category.value || undefined,
      readiness: readiness.value || undefined,
    })
    items.value = res.items || []
  } finally {
    loading.value = false
  }
}

async function loadSims() {
  const res = await benchmarksApi.simulators()
  simulators.value = res.items || []
}

async function markReady(row) {
  try {
    await benchmarksApi.markReady(row.code, { force: false })
    ElMessage.success('已标记 ready')
    loadData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '门禁未通过')
  }
}

function showDetail(row) {
  current.value = row
  drawer.value = true
}

async function showPack(row) {
  try {
    packDetail.value = await benchmarksApi.pack(row.code)
    packDrawer.value = true
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '加载金标失败')
  }
}

async function runSim() {
  if (!simCode.value || !simSuite.value) {
    ElMessage.warning('请选择模拟器与套件')
    return
  }
  simLoading.value = true
  try {
    simResult.value = await benchmarksApi.simulate({
      simulator: simCode.value,
      suite_code: simSuite.value,
    })
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '试跑失败')
  } finally {
    simLoading.value = false
  }
}

onMounted(async () => {
  await loadData()
  await loadSims()
})
</script>

<style scoped>
.toolbar { margin-bottom: 12px; display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.metric { margin-right: 8px; font-size: 12px; }
.metric em { color: var(--el-color-warning); font-style: normal; }
.schema { background: var(--el-fill-color-light); padding: 8px; font-size: 12px; overflow: auto; max-height: 420px; }
.sim-card { margin-top: 16px; }
</style>
