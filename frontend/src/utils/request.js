/**
 * Axios 封装 - 统一请求、拦截器、JWT、错误处理
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import { useUserStore } from '@/stores/user'

// 生产环境：同源部署可不设；前后端分离时在 .env.production 或构建时设置 VITE_API_BASE_URL（如 https://api.example.com）
const baseURL = typeof import.meta.env.VITE_API_BASE_URL !== 'undefined' && import.meta.env.VITE_API_BASE_URL !== ''
  ? import.meta.env.VITE_API_BASE_URL
  : '/api'

const request = axios.create({
  baseURL,
  timeout: 30000
})

export function buildApiUrl(path, params = {}) {
  const normalizedBase = baseURL.endsWith('/') ? baseURL : `${baseURL}/`
  const url = new URL(String(path || '').replace(/^\/+/, ''), new URL(normalizedBase, window.location.origin))
  Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, String(value)))
  return url.toString()
}

function shortenError(msg) {
  const text = String(msg || '请求失败').trim()
  if (!text.includes('Traceback')) return text
  const lines = text.split('\n').map((line) => line.trim()).filter(Boolean)
  return lines[lines.length - 1] || '请求失败'
}

// 请求拦截器 - 添加 JWT
request.interceptors.request.use(
  (config) => {
    const userStore = useUserStore()
    const token = userStore.token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器 - 统一错误处理
request.interceptors.response.use(
  (response) => {
    return response.data
  },
  async (error) => {
    const skipToast = Boolean(error.config?.skipErrorToast || error.response?.config?.skipErrorToast)
    if (error.response) {
      const { status, config } = error.response
      let data = error.response.data
      // blob 下载接口失败时，Axios 仍会把后端 JSON 错误包装成 Blob。
      if (data instanceof Blob) {
        try {
          const text = await data.text()
          data = JSON.parse(text)
          error.response.data = data
        } catch {
          // 非 JSON 响应继续使用统一兜底文案。
        }
      }
      // 后端 HTTPException 返回 message，部分接口返回 detail，兼容两种格式
      let msg = data?.message ?? data?.detail
      if (Array.isArray(msg)) msg = msg.map((m) => m?.msg || JSON.stringify(m)).join('; ')
      else if (typeof msg !== 'string') msg = msg ? JSON.stringify(msg) : '请求失败'
      const displayMsg = shortenError(typeof msg === 'string' ? msg : JSON.stringify(msg))

      if (status === 401) {
        const isAuthEndpoint = config?.url && (config.url.endsWith('auth/login') || config.url.endsWith('auth/register'))
        if (isAuthEndpoint) {
          // 登录/注册接口的 401：仅展示后端文案（如「用户名或密码错误」），不登出、不跳转
          if (!skipToast) ElMessage.error(displayMsg)
        } else {
          // 其它接口 401（如 token 失效）：登出并跳转登录页，优先展示后端文案
          const userStore = useUserStore()
          userStore.logout()
          router.push('/login')
          if (!skipToast) ElMessage.error(displayMsg || '登录已过期，请重新登录')
        }
      } else if (!skipToast) {
        ElMessage.error(displayMsg)
      }
    } else if (!skipToast) {
      ElMessage.error(error.message || '网络错误')
    }
    return Promise.reject(error)
  }
)

export default request
