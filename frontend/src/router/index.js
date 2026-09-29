import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { safeHomePath } from '@/utils/navigation'

const APP_TITLE = '大模型智能评测平台'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true, title: '登录' }
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard.vue'), meta: { permission: 'dashboard:view', title: '工作台' } },
      { path: 'notifications', name: 'NotificationManage', component: () => import('@/views/NotificationManage.vue'), meta: { permission: 'notification:list', title: '通知管理' } },
      { path: 'permissions', name: 'RolePermission', component: () => import('@/views/RolePermission.vue'), meta: { permission: 'role:list', title: '权限管理' } },
      { path: 'profile', name: 'Profile', component: () => import('@/views/Profile.vue'), meta: { title: '个人中心' } },
      { path: 'users', name: 'Users', component: () => import('@/views/Users.vue'), meta: { permission: 'user:list', title: '用户管理' } },
      { path: 'audit', name: 'AuditLog', component: () => import('@/views/AuditLog.vue'), meta: { permission: 'audit:list', title: '操作审计' } },
      { path: 'ops', name: 'Ops', component: () => import('@/views/Ops.vue'), meta: { permission: 'ops:view', title: '运行支撑' } },
      { path: 'api-docs', name: 'ApiDocs', component: () => import('@/views/ApiDocs.vue'), meta: { title: '接口文档' } },
      { path: 'datasets', name: 'Datasets', component: () => import('@/views/Datasets.vue'), meta: { permission: 'dataset:list', title: '评测数据' } },
      { path: 'datasets/:id', name: 'DatasetDetail', component: () => import('@/views/DatasetDetail.vue'), meta: { permission: 'dataset:view', title: '数据集详情' } },
      { path: 'quality', name: 'Quality', component: () => import('@/views/Quality.vue'), meta: { permission: 'quality:list', title: '数据质量' } },
      { path: 'models', name: 'Models', component: () => import('@/views/Models.vue'), meta: { permission: 'model:list', title: '被测模型' } },
      { path: 'prompts', name: 'Prompts', component: () => import('@/views/Prompts.vue'), meta: { permission: 'prompt:list', title: '提示词工程' } },
      { path: 'resources', name: 'Resources', component: () => import('@/views/Resources.vue'), meta: { permission: 'resource:list', title: '工具底座' } },
      { path: 'tasks', name: 'Tasks', component: () => import('@/views/Tasks.vue'), meta: { permission: 'task:list', title: '任务管理' } },
      { path: 'task-templates', name: 'TaskTemplates', component: () => import('@/views/TaskTemplates.vue'), meta: { permission: 'task:list', title: '任务模板' } },
      { path: 'tasks/:id', name: 'TaskDetail', component: () => import('@/views/TaskDetail.vue'), meta: { permission: 'task:view', title: '任务详情' } },
      { path: 'leaderboard', name: 'Leaderboard', component: () => import('@/views/Leaderboard.vue'), meta: { permission: 'leaderboard:view', title: '模型榜单' } },
      { path: 'services', name: 'EvalServices', component: () => import('@/views/EvalServices.vue'), meta: { permission: 'service:list', title: '评测服务' } },
      { path: 'agents', name: 'Agents', component: () => import('@/views/Agents.vue'), meta: { permission: 'agent:list', title: '编排Agent' } }
    ]
  },
  {
    path: '/not-found',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      { path: '', name: 'NotFound', component: () => import('@/views/NotFound.vue'), meta: { title: '页面不存在' } }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      { path: '', name: 'NotFoundCatchAll', component: () => import('@/views/NotFound.vue'), meta: { title: '页面不存在' } }
    ]
  }
]

function hasRoutePermission(userStore, permission) {
  if (Array.isArray(permission)) {
    return userStore.hasAnyPermission(...permission)
  }
  return userStore.hasPermission(permission)
}

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, _from, next) => {
  const userStore = useUserStore()
  if (!to.meta.public && !userStore.isLoggedIn()) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }
  if (to.path === '/login' && userStore.isLoggedIn()) {
    const redirect = typeof to.query.redirect === 'string' ? to.query.redirect : ''
    next(redirect || safeHomePath(router))
    return
  }
  if (to.meta.permission && !hasRoutePermission(userStore, to.meta.permission)) {
    next({
      path: '/not-found',
      query: { reason: 'forbidden', from: to.fullPath },
    })
    return
  }
  next()
})

router.afterEach((to) => {
  const title = to.meta.title
  document.title = title ? `${title} - ${APP_TITLE}` : APP_TITLE
})

export default router
