import { useUserStore } from '@/stores/user'

/**
 * 权限 composable - 用于页面和按钮显隐
 * @returns { hasPermission, hasAnyPermission, isAdmin }
 */
export function usePermission() {
  const userStore = useUserStore()

  function hasPermission(perm) {
    return userStore.hasPermission(perm)
  }

  function hasAnyPermission(...perms) {
    return userStore.hasAnyPermission(...perms)
  }

  return {
    hasPermission,
    hasAnyPermission,
    isAdmin: () => userStore.isAdmin()
  }
}
