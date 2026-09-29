<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">安全可信评测</h2>
        <p class="page-desc">风险 / 标识 / 对齐 / 幻觉四类正式裁判；空输出与缺证据不得判真；探索集不入固定比较；不做自动法律结论。</p>
      </div>
      <el-button type="primary" :loading="calLoading" v-if="userStore.hasPermission('task:edit')" @click="runCalibrate">重新校准</el-button>
    </div>

    <PageAsyncState
      v-if="['loading', 'error', 'forbidden', 'uncreated'].includes(pageState)"
      :state="pageState"
      :errorMessage="loadError"
    />
    <el-row v-else :gutter="16">
      <el-col :span="14">
        <el-card>
          <template #header>类别表现（人工金标一致率）</template>
          <el-table v-loading="loading" :data="categories" stripe>
            <template #empty>
              <EmptyState type="default" title="暂无安全类别" description="加载成功后将显示风险/标识/对齐/幻觉类别。" :show-action="false" />
            </template>
            <el-table-column prop="category" label="类别" width="120" />
            <el-table-column prop="rule_version" label="规则版本" min-width="140" />
            <el-table-column label="固定/探索" width="100">
              <template #default="{ row }">{{ row.fixed_count }}/{{ row.explore_count }}</template>
            </el-table-column>
            <el-table-column label="一致率" width="100">
              <template #default="{ row }">{{ ((row.agreement || 0) * 100).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column label="校准" width="90">
              <template #default="{ row }">
                <el-tag :type="row.calibrated ? 'success' : 'danger'" size="small">{{ row.calibrated ? '通过' : '未过' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openSet(row.category, 'fixed')">固定集</el-button>
                <el-button link type="primary" size="small" @click="openSet(row.category, 'explore')">探索集</el-button>
                <el-button link type="primary" size="small" @click="openTryScore(row)">试评</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card class="mt">
          <template #header>候选题库双验证（不得直入 fixed）</template>
          <el-table :data="candidates" stripe>
            <el-table-column prop="id" label="ID" min-width="140" />
            <el-table-column prop="category" label="类" width="110" />
            <el-table-column prop="status" label="状态" width="110" />
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button
                  v-if="userStore.hasPermission('task:edit')"
                  link
                  type="primary"
                  size="small"
                  @click="validateCand(row)"
                >双验证</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="10">
        <el-card>
          <template #header>专家复核队列</template>
          <el-table :data="reviews" stripe max-height="360">
            <el-table-column prop="id" label="单号" width="90" />
            <el-table-column prop="sample_id" label="样本" min-width="110" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status === 'pending' ? 'warning' : 'success'">{{ reviewStatusCn(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button
                  v-if="row.status === 'pending' && userStore.hasPermission('task:edit')"
                  link
                  type="primary"
                  size="small"
                  @click="openReview(row)"
                >复核</el-button>
                <el-button v-else link size="small" @click="openReview(row)">查看</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card class="mt">
          <template #header>试评结果</template>
          <pre class="schema">{{ scoreResult ? JSON.stringify(scoreResult, null, 2) : '在「试评」中输入候选输出后查看' }}</pre>
        </el-card>
      </el-col>
    </el-row>

    <el-drawer v-model="setDrawer" :title="`样本集 ${setCategory} / ${setType === 'fixed' ? '固定集' : '探索集'}`" size="560px">
      <el-alert
        :type="setType === 'explore' ? 'warning' : 'info'"
        :closable="false"
        :title="setType === 'explore' ? '探索集仅供诊断，不得进入固定榜单比较。' : '固定集用于正式可比评测。'"
        style="margin-bottom: 12px"
      />
      <pre class="schema">{{ JSON.stringify(setSamples, null, 2) }}</pre>
    </el-drawer>

    <el-drawer v-model="reviewDrawer" title="专家复核" size="480px">
      <template v-if="activeReview">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="单号">{{ activeReview.id }}</el-descriptions-item>
          <el-descriptions-item label="类别">{{ activeReview.category }}</el-descriptions-item>
          <el-descriptions-item label="样本">{{ activeReview.sample_id }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ reviewStatusCn(activeReview.status) }}</el-descriptions-item>
        </el-descriptions>
        <h4>候选输出</h4>
        <pre class="schema">{{ activeReview.prediction || '（空）' }}</pre>
        <h4>备注</h4>
        <p class="note">{{ activeReview.note || '—' }}</p>
        <template v-if="activeReview.status === 'pending' && userStore.hasPermission('task:edit')">
          <el-form label-width="88px" class="mt">
            <el-form-item label="人工标签" required>
              <el-select v-model="reviewForm.expert_label" style="width: 100%">
                <el-option label="通过" value="approved" />
                <el-option label="驳回" value="rejected" />
                <el-option label="需补证" value="needs_evidence" />
              </el-select>
            </el-form-item>
            <el-form-item label="理由">
              <el-input v-model="reviewForm.note" type="textarea" rows="3" placeholder="填写判断依据；驳回/补证时必填" />
            </el-form-item>
            <el-button type="primary" :loading="resolving" @click="submitReview">提交复核</el-button>
          </el-form>
        </template>
        <template v-else-if="activeReview.expert_label">
          <h4>已裁定</h4>
          <p>{{ activeReview.expert_label }} · {{ activeReview.note || '无备注' }}</p>
        </template>
      </template>
    </el-drawer>

    <el-dialog v-model="tryDialog" title="试评" width="560px">
      <el-form label-width="88px">
        <el-form-item label="类别">{{ tryForm.category }}</el-form-item>
        <el-form-item label="样本">
          <el-select v-model="tryForm.sample_id" filterable style="width: 100%" @change="onTrySample">
            <el-option v-for="s in trySamples" :key="s.id" :label="s.id" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="候选输出">
          <el-input v-model="tryForm.prediction" type="textarea" rows="4" placeholder="输入实际模型输出，勿默认填入 good 示例" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="tryDialog = false">取消</el-button>
        <el-button type="primary" :loading="scoring" @click="submitTryScore">评分</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { safetyApi } from '@/api'
import { useUserStore } from '@/stores/user'
import EmptyState from '@/components/EmptyState.vue'
import PageAsyncState from '@/components/PageAsyncState.vue'
import { deriveAsyncState } from '@/utils/asyncState.js'

const userStore = useUserStore()
const loading = ref(false)
const loadError = ref('')
const createdOnce = ref(false)
const calLoading = ref(false)
const categories = ref([])
const reviews = ref([])
const candidates = ref([])
const scoreResult = ref(null)
const setDrawer = ref(false)
const setCategory = ref('')
const setType = ref('fixed')
const setSamples = ref([])

const reviewDrawer = ref(false)
const activeReview = ref(null)
const resolving = ref(false)
const reviewForm = ref({ expert_label: 'approved', note: '' })

const tryDialog = ref(false)
const trySamples = ref([])
const scoring = ref(false)
const tryForm = ref({ category: '', sample_id: '', prediction: '' })

function reviewStatusCn(s) {
  return ({ pending: '待复核', resolved: '已复核', closed: '已关闭' }[s] || s)
}

const pageState = computed(() => deriveAsyncState({
  loading: loading.value && !createdOnce.value,
  error: loadError.value,
  forbidden: false,
  items: categories.value,
  createdOnce: createdOnce.value,
}))

function loadErr(e, fallback) {
  const d = e?.response?.data
  const msg = d?.message || d?.detail || e?.message
  return typeof msg === 'string' && msg ? msg : fallback
}

async function loadAll() {
  loading.value = true
  loadError.value = ''
  try {
    const [c, r, cand] = await Promise.all([
      safetyApi.categories(),
      safetyApi.reviews(),
      safetyApi.candidates(),
    ])
    categories.value = c.items || []
    reviews.value = r.items || []
    candidates.value = cand.items || []
    createdOnce.value = true
  } catch (e) {
    loadError.value = loadErr(e, '安全评测加载失败')
  } finally {
    loading.value = false
  }
}

async function runCalibrate() {
  calLoading.value = true
  try {
    const res = await safetyApi.calibrate()
    if (res.ok) ElMessage.success(`校准通过，最低一致率 ${(res.min_agreement * 100).toFixed(1)}%`)
    else ElMessage.warning('校准未全部达标')
    await loadAll()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '校准失败')
  } finally {
    calLoading.value = false
  }
}

async function openSet(category, type) {
  const res = await safetyApi.getSet(category, { set_type: type })
  setCategory.value = category
  setType.value = type
  setSamples.value = res.samples || []
  setDrawer.value = true
}

function openReview(row) {
  activeReview.value = row
  reviewForm.value = { expert_label: 'approved', note: '' }
  reviewDrawer.value = true
}

async function submitReview() {
  if (!reviewForm.value.expert_label) {
    ElMessage.warning('请选择人工标签')
    return
  }
  if (reviewForm.value.expert_label !== 'approved' && !(reviewForm.value.note || '').trim()) {
    ElMessage.warning('驳回或需补证时请填写理由')
    return
  }
  resolving.value = true
  try {
    await safetyApi.resolveReview(activeReview.value.id, {
      expert_label: reviewForm.value.expert_label,
      note: reviewForm.value.note,
    })
    ElMessage.success('已提交复核')
    reviewDrawer.value = false
    await loadAll()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '复核失败')
  } finally {
    resolving.value = false
  }
}

async function openTryScore(row) {
  const set = await safetyApi.getSet(row.category, { set_type: 'fixed' })
  trySamples.value = set.samples || []
  tryForm.value = {
    category: row.category,
    sample_id: trySamples.value[0]?.id || '',
    prediction: '',
  }
  tryDialog.value = true
}

function onTrySample() {
  tryForm.value.prediction = ''
}

async function submitTryScore() {
  if (!(tryForm.value.prediction || '').trim()) {
    ElMessage.warning('请输入候选输出')
    return
  }
  scoring.value = true
  try {
    scoreResult.value = await safetyApi.score({
      category: tryForm.value.category,
      sample_id: tryForm.value.sample_id,
      prediction: tryForm.value.prediction,
    })
    tryDialog.value = false
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '试评失败')
  } finally {
    scoring.value = false
  }
}

async function validateCand(row) {
  const res = await safetyApi.validateCandidate(row.id)
  if (res.ok) ElMessage.success('双验证通过（仍非 fixed）')
  else ElMessage.warning('双验证未通过')
  await loadAll()
}

onMounted(loadAll)
</script>

<style scoped>
.mt { margin-top: 16px; }
.schema { background: var(--el-fill-color-light); padding: 8px; font-size: 12px; overflow: auto; max-height: 420px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.note { color: var(--el-text-color-secondary); font-size: 13px; }
h4 { margin: 16px 0 8px; font-size: 14px; }
</style>
