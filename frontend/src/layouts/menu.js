/** 侧栏菜单 */
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
    index: 'base',
    title: '评测底座',
    icon: 'Box',
    children: [
      { index: '/datasets', title: '评测数据', icon: 'Collection', permission: 'dataset:list', match: '/datasets' },
      { index: '/quality', title: '数据质量', icon: 'CircleCheck', permission: 'quality:list' },
      { index: '/models', title: '被测模型', icon: 'Cpu', permission: 'model:list' },
      { index: '/prompts', title: '提示词工程', icon: 'ChatLineSquare', permission: 'prompt:list' },
      { index: '/resources', title: '工具底座', icon: 'SetUp', permission: 'resource:list' }
    ]
  },
  {
    index: 'eval',
    title: '评测任务',
    icon: 'List',
    children: [
      { index: '/tasks', title: '任务管理', icon: 'Finished', permission: 'task:list', match: '/tasks' },
      { index: '/task-templates', title: '任务模板', icon: 'Collection', permission: 'task:list' },
      { index: '/benchmarks', title: '基准套件', icon: 'Medal', permission: 'task:list' },
      { index: '/safety', title: '安全可信', icon: 'Warning', permission: 'task:list' },
      { index: '/services', title: '评测服务', icon: 'Ticket', permission: 'service:list' },
      { index: '/agents', title: '编排Agent', icon: 'Connection', permission: 'agent:list' }
    ]
  },
  {
    index: 'apps',
    title: '应用服务',
    icon: 'Trophy',
    children: [
      { index: '/leaderboard', title: '模型榜单', icon: 'Trophy', permission: 'leaderboard:view' }
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
      { index: '/ops', title: '运行支撑', icon: 'Monitor', permission: 'ops:view' },
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
