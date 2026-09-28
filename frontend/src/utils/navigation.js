import { useUserStore } from '@/stores/user'

const CANDIDATES = [
  { path: '/dashboard', permission: 'dashboard:view' },
  { path: '/agents', permission: 'agent:list' },
  { path: '/tasks', permission: 'task:list' },
  { path: '/datasets', permission: 'dataset:list' },
  { path: '/models', permission: 'model:list' },
  { path: '/resources', permission: 'resource:list' },
  { path: '/services', permission: 'service:list' },
  { path: '/leaderboard', permission: 'leaderboard:view' },
  { path: '/ops', permission: 'ops:view' },
  { path: '/users', permission: 'user:list' },
  { path: '/notifications', permission: 'notification:list' },
  { path: '/audit', permission: 'audit:list' },
  { path: '/profile', permission: null },
]

function allowed(userStore, permission) {
  if (!permission) return true
  if (Array.isArray(permission)) return userStore.hasAnyPermission(...permission)
  return userStore.hasPermission(permission)
}

/** 首个当前用户可访问的业务页（避免无 dashboard 权限时死循环） */
export function firstAccessiblePath(_router, userStore = useUserStore()) {
  for (const c of CANDIDATES) {
    if (allowed(userStore, c.permission)) return c.path
  }
  return '/profile'
}

export function safeHomePath(router) {
  return firstAccessiblePath(router)
}
