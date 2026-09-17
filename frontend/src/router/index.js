import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'

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
      { path: 'api-docs', name: 'ApiDocs', component: () => import('@/views/ApiDocs.vue'), meta: { title: '接口文档' } }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      { path: '', name: 'NotFoundPage', component: () => import('@/views/NotFound.vue'), meta: { title: '页面不存在' } }
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
  } else if (to.path === '/login' && userStore.isLoggedIn()) {
    next('/dashboard')
  } else if (to.meta.permission && !hasRoutePermission(userStore, to.meta.permission)) {
    next('/dashboard')
  } else {
    next()
  }
})

router.afterEach((to) => {
  const title = to.meta.title
  document.title = title ? `${title} - ${APP_TITLE}` : APP_TITLE
})

export default router
