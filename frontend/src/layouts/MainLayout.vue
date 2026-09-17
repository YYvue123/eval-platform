<template>
  <el-container class="main-layout">
    <el-aside :width="asideWidth" class="aside">
      <div class="logo">
        <el-icon><Cpu /></el-icon>
        <span v-show="!collapsed">评测平台</span>
      </div>
      <div class="menu-scroll">
      <el-menu
        ref="menuRef"
        :default-active="activeMenu"
        :default-openeds="openedMenus"
        :collapse="collapsed"
        :collapse-transition="false"
        router
        :background-color="menuBg"
        text-color="#bfcbd9"
        active-text-color="var(--color-primary)"
      >
        <template v-for="group in visibleMenuGroups" :key="group.index">
          <el-menu-item v-if="group.flat && group.children[0]" :index="group.children[0].index">
            <el-icon><component :is="group.children[0].icon || group.icon" /></el-icon>
            <span>{{ group.children[0].title }}</span>
          </el-menu-item>
          <el-sub-menu v-else :index="group.index">
            <template #title>
              <el-icon><component :is="group.icon" /></el-icon>
              <span>{{ group.title }}</span>
            </template>
            <el-menu-item v-for="item in group.children" :key="item.index" :index="item.index">
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.title }}</span>
            </el-menu-item>
          </el-sub-menu>
        </template>
      </el-menu>
      </div>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-tooltip :content="collapsed ? '展开菜单' : '收起菜单'" placement="bottom">
            <el-button :icon="collapsed ? Expand : Fold" circle size="small" @click="toggleCollapsed" />
          </el-tooltip>
          <el-breadcrumb v-if="breadcrumbs.length" class="breadcrumb" separator="/">
            <el-breadcrumb-item v-for="(item, i) in breadcrumbs" :key="`${item.path}-${i}`">
              <router-link v-if="i < breadcrumbs.length - 1" :to="item.path">{{ item.title }}</router-link>
              <span v-else>{{ item.title }}</span>
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-tooltip :content="themeStore.isDark ? '切换亮色' : '切换暗色'" placement="bottom">
            <el-button :icon="themeStore.isDark ? Sunny : Moon" circle size="small" @click="themeStore.toggle" />
          </el-tooltip>
          <NotificationCenter />
          <el-tag v-if="userStore.isAdmin()" type="danger" size="small">管理员</el-tag>
          <el-tag v-else-if="userStore.roleCode === 'researcher'" type="success" size="small">评测人员</el-tag>
          <el-tag v-else type="info" size="small">访客</el-tag>
          <el-dropdown trigger="click" class="user-dropdown" @command="handleUserCommand">
            <span class="user-trigger">
              <el-avatar :size="32" :src="userStore.avatarDisplayUrl" class="header-avatar">
                {{ (userStore.displayName || userStore.username || 'U').charAt(0).toUpperCase() }}
              </el-avatar>
              <span class="username">{{ userStore.displayName || userStore.username }}</span>
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  <el-icon><User /></el-icon>
                  个人设置
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><SwitchButton /></el-icon>
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main">
        <router-view v-slot="{ Component }">
          <Suspense>
            <component :is="Component" />
            <template #fallback>
              <div class="loading-wrap">
                <el-icon class="is-loading" :size="32"><Loading /></el-icon>
                <p>加载中...</p>
              </div>
            </template>
          </Suspense>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { onMounted, computed, ref, watch } from 'vue'
import { Cpu, Sunny, Moon, ArrowDown, User, SwitchButton, Loading, Fold, Expand } from '@element-plus/icons-vue'
import NotificationCenter from '@/components/NotificationCenter.vue'
import { useUserStore } from '@/stores/user'
import { useThemeStore } from '@/stores/theme'
import { useRouter, useRoute } from 'vue-router'
import { MENU_GROUPS, canSeeMenuItem, findMenuContext } from './menu'

const userStore = useUserStore()
const themeStore = useThemeStore()
const router = useRouter()
const route = useRoute()

const COLLAPSE_KEY = 'llm_sidebar_collapsed'
const menuRef = ref()
const collapsed = ref(localStorage.getItem(COLLAPSE_KEY) === '1')
const asideWidth = computed(() => (collapsed.value ? '64px' : '240px'))
const menuBg = computed(() => themeStore.isDark ? '#0f172a' : '#1e293b')

function toggleCollapsed() {
  collapsed.value = !collapsed.value
  localStorage.setItem(COLLAPSE_KEY, collapsed.value ? '1' : '0')
}

const visibleMenuGroups = computed(() =>
  MENU_GROUPS
    .map((group) => ({
      ...group,
      children: group.children.filter((item) =>
        canSeeMenuItem(userStore.hasPermission, userStore.hasAnyPermission, item)
      )
    }))
    .filter((group) => group.children.length > 0)
)

const activeMenu = computed(() => {
  const ctx = findMenuContext(route.path)
  return ctx?.child.index || route.path
})

const openedMenus = computed(() => {
  const ctx = findMenuContext(route.path)
  return ctx ? [ctx.group.index] : []
})

const breadcrumbs = computed(() => {
  const ctx = findMenuContext(route.path)
  if (ctx) {
    const crumbs = []
    if (!ctx.group.flat && ctx.group.title !== ctx.child.title) {
      crumbs.push({ title: ctx.group.title, path: ctx.child.index })
    }
    crumbs.push({ title: ctx.child.title, path: ctx.child.index })
    if (route.meta?.title && route.meta.title !== ctx.child.title) {
      crumbs.push({ title: route.meta.title, path: route.path })
    }
    return crumbs
  }
  if (route.meta?.title) {
    return [{ title: route.meta.title, path: route.path }]
  }
  return []
})

onMounted(() => {
  userStore.fetchUserInfo()
})

watch(
  () => [route.path, visibleMenuGroups.value.length],
  () => {
    const ctx = findMenuContext(route.path)
    if (ctx && !ctx.group.flat && menuRef.value?.open) {
      menuRef.value.open(ctx.group.index)
    }
  },
  { flush: 'post' }
)

function handleUserCommand(cmd) {
  if (cmd === 'profile') {
    router.push('/profile')
  } else if (cmd === 'logout') {
    userStore.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.main-layout {
  height: 100vh;
}
.aside {
  background: var(--bg-sidebar);
  transition: background var(--transition-normal), width var(--transition-normal);
  border-right: none !important;
  box-shadow: none !important;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.aside :deep(.el-menu) {
  width: 100%;
}
.aside :deep(.el-menu--collapse) {
  width: 64px;
}
.menu-scroll {
  flex: 1;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.18) transparent;
}
.menu-scroll::-webkit-scrollbar {
  width: 6px;
}
.menu-scroll::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.18);
  border-radius: 6px;
}
.menu-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}
.menu-scroll::-webkit-scrollbar-button {
  display: none;
  width: 0;
  height: 0;
}
.aside :deep(.el-menu) {
  border-right: none !important;
}
.aside :deep(.el-sub-menu__title) {
  color: #bfcbd9 !important;
}
.aside :deep(.el-sub-menu .el-menu-item) {
  min-width: 0;
}
.logo {
  height: 60px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
}
.header {
  background: var(--bg-header);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  transition: background var(--transition-normal);
  border-bottom: 1px solid var(--border-color);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex: 1;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.user-dropdown {
  cursor: pointer;
}
.user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
}
.header-avatar {
  flex-shrink: 0;
  background: var(--el-color-primary);
}
.username {
  color: var(--text-secondary);
  font-size: 14px;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.main {
  background: var(--bg-page);
  padding: 20px;
  overflow-y: auto;
  transition: background var(--transition-normal);
}
.breadcrumb {
  font-size: 14px;
  line-height: 1;
}
.breadcrumb :deep(.el-breadcrumb__item:last-child .el-breadcrumb__inner) {
  color: var(--text-secondary);
  font-weight: 500;
}
.breadcrumb :deep(.el-breadcrumb__inner a) {
  color: var(--text-secondary);
  font-weight: 400;
}
.breadcrumb :deep(.el-breadcrumb__inner a:hover) {
  color: var(--color-primary);
}
.loading-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px;
  color: var(--text-secondary);
}
</style>
