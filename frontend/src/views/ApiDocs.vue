<template>
  <div class="api-docs-page">
    <el-card shadow="never" class="swagger-card">
      <template #header>
        <div class="card-head">
          <span>全部接口（Swagger）</span>
          <el-link type="primary" :href="docsUrl" target="_blank">新窗口打开 /docs</el-link>
        </div>
      </template>
      <p class="hint">由 FastAPI 根据路由自动生成。平台管理接口使用登录 JWT（Authorize 中的 HTTPBearer）。</p>
      <PageAsyncState
        v-if="loadError"
        state="error"
        :errorMessage="loadError"
      />
      <p v-if="loadError" class="hint">下一步：确认后端已启动后刷新本页，或使用上方链接直接打开 /docs。</p>
      <div v-else ref="swaggerEl" class="swagger-host" />
    </el-card>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import SwaggerUI from 'swagger-ui-dist/swagger-ui-es-bundle.js'
import 'swagger-ui-dist/swagger-ui.css'
import PageAsyncState from '@/components/PageAsyncState.vue'

const origin = window.location.origin
const docsUrl = `${origin}/docs`
const swaggerEl = ref()
const loadError = ref('')
let swaggerRoot = null

function currentToken() {
  return localStorage.getItem('eval_token') || sessionStorage.getItem('eval_token') || ''
}

onMounted(async () => {
  loadError.value = ''
  try {
    const probe = await fetch(`${origin}/openapi.json`)
    if (!probe.ok) {
      throw new Error(`无法加载 OpenAPI（HTTP ${probe.status}）`)
    }
    swaggerRoot = SwaggerUI({
      domNode: swaggerEl.value,
      url: '/openapi.json',
      persistAuthorization: true,
      docExpansion: 'list',
      defaultModelsExpandDepth: 0,
      tryItOutEnabled: true,
      requestInterceptor: (req) => {
        const token = currentToken()
        const url = String(req.url || '')
        const hasAuth = req.headers && (req.headers.Authorization || req.headers.authorization)
        if (token && url.includes('/api/') && !url.endsWith('/openapi.json') && !hasAuth) {
          req.headers = req.headers || {}
          req.headers.Authorization = `Bearer ${token}`
        }
        return req
      }
    })
  } catch (e) {
    loadError.value = e?.message || 'Swagger 文档加载失败'
  }
})

onBeforeUnmount(() => {
  swaggerRoot = null
})
</script>

<style scoped>
.api-docs-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.swagger-host {
  min-height: 480px;
}
.swagger-host :deep(.swagger-ui) {
  font-family: inherit;
}
.swagger-host :deep(.information-container) {
  display: none;
}
.swagger-host :deep(.scheme-container) {
  background: transparent;
  box-shadow: none;
  padding: 0 0 12px;
}
</style>
