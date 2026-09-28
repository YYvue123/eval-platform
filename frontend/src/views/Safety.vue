<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">安全可信评测</h2>
        <p class="page-desc">风险 / 标识 / 对齐 / 幻觉四类正式裁判；空输出与缺证据不得判真；探索集不入固定比较；不做自动法律结论。</p>
      </div>
      <el-button type="primary" :loading="calLoading" v-if="userStore.hasPermission('task:edit')" @click="runCalibrate">重新校准</el-button>
    </div>

    <el-row :gutter="16">
      <el-col :span="14">
        <el-card>
          <template #header>类别表现（人工金标一致率）</template>
          <el-table v-loading="loading" :data="categories" stripe>
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
            <el-table-column label="操作" width="160">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openSet(row.category, 'fixed')">固定集</el-button>
                <el-button link type="primary" size="small" @click="tryScore(row)">试评</el-button>
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
          <template #header>专家复核</template>
          <el-table :data="reviews" stripe max-height="360">
            <el-table-column prop="id" label="单号" width="90" />
            <el-table-column prop="sample_id" label="样本" min-width="110" />
            <el-table-column prop="status" label="状态" width="90" />
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button
                  v-if="row.status === 'pending' && userStore.hasPermission('task:edit')"
                  link
                  type="primary"
                  size="small"
                  @click="resolve(row)"
                >通过</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card class="mt">
          <template #header>试评结果</template>
          <pre class="schema">{{ scoreResult ? JSON.stringify(scoreResult, null, 2) : '选择类别「试评」查看' }}</pre>
        </el-card>
      </el-col>
    </el-row>

    <el-drawer v-model="setDrawer" :title="`样本集 ${setCategory}/${setType}`" size="560px">
      <pre class="schema">{{ JSON.stringify(setSamples, null, 2) }}</pre>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { safetyApi } from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const loading = ref(false)
const calLoading = ref(false)
const categories = ref([])
const reviews = ref([])
const candidates = ref([])
const scoreResult = ref(null)
const setDrawer = ref(false)
const setCategory = ref('')
const setType = ref('fixed')
const setSamples = ref([])

async function loadAll() {
  loading.value = true
  try {
    const [c, r, cand] = await Promise.all([
      safetyApi.categories(),
      safetyApi.reviews(),
      safetyApi.candidates(),
    ])
    categories.value = c.items || []
    reviews.value = r.items || []
    candidates.value = cand.items || []
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

async function tryScore(row) {
  const set = await safetyApi.getSet(row.category, { set_type: 'fixed' })
  const sample = (set.samples || [])[0]
  if (!sample) return
  const pred =
    sample.prediction_examples?.good ||
    sample.prediction_examples?.good_formal ||
    '无法提供'
  scoreResult.value = await safetyApi.score({
    category: row.category,
    sample_id: sample.id,
    prediction: pred,
  })
}

async function resolve(row) {
  await safetyApi.resolveReview(row.id, { expert_label: 'approved', note: '专家通过' })
  ElMessage.success('已复核')
  await loadAll()
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
</style>
