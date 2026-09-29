import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/docs': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/redoc': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/openapi.json': { target: 'http://127.0.0.1:8001', changeOrigin: true },
    },
  },
})
