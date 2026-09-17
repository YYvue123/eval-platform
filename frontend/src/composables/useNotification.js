/**
 * 全局通知 composable - 统一使用 ElNotification（Toast 提示）
 * 通知中心数据来自管理后台发送的系统通知，由 NotificationCenter 从 API 获取
 */
import { ElNotification, ElMessage } from 'element-plus'

export function useNotification() {
  const success = (msg) => ElNotification.success({ title: '成功', message: msg, duration: 3000 })
  const warning = (msg) => ElNotification.warning({ title: '警告', message: msg, duration: 4000 })
  const error = (msg) => ElNotification.error({ title: '错误', message: msg, duration: 5000 })
  const info = (msg) => ElNotification.info({ title: '提示', message: msg, duration: 3000 })
  const notify = (options) => {
    if (typeof options === 'string') {
      ElNotification({ title: '通知', message: options })
      return
    }
    ElNotification({ title: '通知', duration: 4500, ...options })
  }
  return { notify, success, warning, error, info, message: ElMessage }
}
