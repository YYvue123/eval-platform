import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import '@/styles/variables.css'
import '@/styles/global.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import App from './App.vue'
import router from './router'
import permissionDirective from './directives/permission'

const app = createApp(App)
app.directive('permission', permissionDirective)
const pinia = createPinia()

// 注册所有 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(pinia)
app.use(router)
app.use(ElementPlus, { locale: zhCn })

// 初始化主题（在挂载前应用，避免闪烁）
const theme = localStorage.getItem('eval-theme')
if (theme === 'dark') {
  document.documentElement.classList.add('dark')
}

app.mount('#app')
