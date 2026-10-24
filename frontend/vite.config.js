import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  build: {
    // swagger-ui-dist 仅在接口文档页懒加载，体积超过 Vite 默认 500 kB 属预期
    chunkSizeWarningLimit: 1600
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true
      },
      '/docs': {
        target: apiTarget,
        changeOrigin: true
      },
      '/redoc': {
        target: apiTarget,
        changeOrigin: true
      },
      '/openapi.json': {
        target: apiTarget,
        changeOrigin: true
      }
    }
  }
})
