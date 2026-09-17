<template>
  <div class="not-found">
    <div class="not-found-content">
      <div class="code">404</div>
      <h1 class="title">页面不存在</h1>
      <p class="desc">您访问的地址无效或已被移除，请检查链接或返回首页。</p>
      <el-button type="primary" @click="goHome">返回首页</el-button>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

function goHome() {
  router.push('/dashboard')
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
</style>
