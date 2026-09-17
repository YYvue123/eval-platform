import { useUserStore } from '@/stores/user'

/**
 * v-permission 指令 - 无权限时移除元素
 * 用法: v-permission="'dataset:create'" 或 v-permission="['dataset:create', 'dataset:delete']"
 * 多权限为或关系：有任一权限即显示
 */
export default {
  mounted(el, binding) {
    const { value } = binding
    const userStore = useUserStore()
    const check = () => {
      if (!value) return true
      if (userStore.isAdmin()) return true
      const perms = Array.isArray(value) ? value : [value]
      return perms.some((p) => userStore.hasPermission(p))
    }
    if (!check()) {
      el.parentNode?.removeChild(el)
    }
  }
}
