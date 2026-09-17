import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const THEME_KEY = 'eval-theme'

export const useThemeStore = defineStore('theme', () => {
  const isDark = ref(localStorage.getItem(THEME_KEY) === 'dark')

  function toggle() {
    isDark.value = !isDark.value
    apply()
  }

  function setDark(value) {
    isDark.value = !!value
    apply()
  }

  function apply() {
    if (isDark.value) {
      document.documentElement.classList.add('dark')
      localStorage.setItem(THEME_KEY, 'dark')
    } else {
      document.documentElement.classList.remove('dark')
      localStorage.setItem(THEME_KEY, 'light')
    }
  }

  // 初始化时应用
  apply()

  return { isDark, toggle, setDark }
})
