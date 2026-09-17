/** 侧栏菜单：一级为功能分类，二级为现有页面 */
export const MENU_GROUPS = [
  {
    index: 'overview',
    title: '工作台',
    icon: 'DataAnalysis',
    flat: true,
    children: [
      { index: '/dashboard', title: '工作台', icon: 'DataAnalysis', permission: 'dashboard:view' }
    ]
  },
  {
    index: 'system',
    title: '系统管理',
    icon: 'Setting',
    children: [
      { index: '/users', title: '用户管理', icon: 'Avatar', permission: 'user:list' },
      { index: '/profile', title: '个人中心', icon: 'User', permission: null },
      { index: '/permissions', title: '权限管理', icon: 'Key', permission: 'role:list' },
      { index: '/notifications', title: '通知管理', icon: 'Bell', permission: 'notification:list' },
      { index: '/audit', title: '操作审计', icon: 'DocumentChecked', permission: 'audit:list' },
      { index: '/api-docs', title: '接口文档', icon: 'DocumentCopy', permission: null }
    ]
  }
]

export function itemMatchesPath(item, path) {
  const prefix = item.match || item.index
  if (prefix === '/') return path === '/'
  return path === item.index || path.startsWith(`${prefix}/`)
}

export function findMenuContext(path) {
  for (const group of MENU_GROUPS) {
    const child = group.children.find((c) => itemMatchesPath(c, path))
    if (child) return { group, child }
  }
  return null
}

export function canSeeMenuItem(hasPermission, hasAnyPermission, item) {
  if (!item.permission) return true
  if (Array.isArray(item.permission)) return hasAnyPermission(...item.permission)
  return hasPermission(item.permission)
}
