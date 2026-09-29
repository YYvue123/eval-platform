<template>
  <div class="not-found">
    <div class="not-found-content">
      <div class="code">{{ forbidden ? '403' : '404' }}</div>
      <h1 class="title">{{ forbidden ? '无权访问该页面' : '页面不存在' }}</h1>
      <p class="desc">
        {{
          forbidden
            ? '当前账号没有权限访问该模块。请联系管理员开通，或返回可访问工作台。'
            : '您访问的地址无效或已被移除。可返回上一页，或进入可访问工作台。'
        }}
      </p>
      <p v-if="fromPath" class="desc from-path">来源：{{ fromPath }}</p>
      <div class="actions">
        <el-button @click="goBack">返回上一页</el-button>
        <el-button type="primary" @click="goHome">可访问工作台</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { safeHomePath } from '@/utils/navigation'

const router = useRouter()
const route = useRoute()
const forbidden = computed(() => route.query.reason === 'forbidden' || !!route.query.denied)
const fromPath = computed(() => (typeof route.query.from === 'string' ? route.query.from : ''))

function goBack() {
  if (window.history.length > 1) router.back()
  else goHome()
}

function goHome() {
  router.push(safeHomePath(router))
}
</script>

<style scoped>
.not-found {
  min-height: 60vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.not-found-content {
  text-align: center;
  max-width: 420px;
}
.code {
  font-size: 72px;
  font-weight: 700;
  line-height: 1;
  color: var(--el-color-info-light-5);
  margin-bottom: 16px;
}
.title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px;
}
.desc {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0 0 24px;
  line-height: 1.6;
}
.actions { display: flex; gap: 8px; justify-content: center; }
</style>
