<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">任务模板库</h2>
        <p class="page-desc">语言/语音/视觉/多模态、11 类场景、14 个行业、4 类安全基准。每项绑定试点数据集、标尺与指标权重。</p>
      </div>
    </div>
    <el-card>
      <el-radio-group v-model="category" style="margin-bottom: 12px" @change="loadData">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="capability">基础能力</el-radio-button>
        <el-radio-button value="scene">场景应用</el-radio-button>
        <el-radio-button value="industry">行业专项</el-radio-button>
        <el-radio-button value="safety">安全可信</el-radio-button>
      </el-radio-group>
      <el-table :data="items" stripe>
        <el-table-column prop="name" label="模板" min-width="160" />
        <el-table-column prop="category" label="分类" width="100" />
        <el-table-column prop="scene" label="场景" width="120" />
        <el-table-column prop="industry" label="行业" width="110" />
        <el-table-column prop="judge_resource_id" label="默认裁判" min-width="180" />
        <el-table-column prop="rubric" label="标尺" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button v-if="userStore.hasPermission('task:create')" link type="primary" @click="useTpl(row)">使用</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { tasksApi } from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const router = useRouter()
const items = ref([])
const category = ref('')

async function loadData() {
  const res = await tasksApi.templates({ category: category.value })
  items.value = res.items || []
}

function useTpl(row) {
  router.push({ path: '/tasks', query: { template: row.code } })
}

onMounted(loadData)
</script>
