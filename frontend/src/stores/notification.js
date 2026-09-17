import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { notificationsApi } from '@/api'

export const useNotificationStore = defineStore('notification', () => {
  const list = ref([])
  const unreadCount = ref(0)

  const unreadCountDisplay = computed(() => Math.min(unreadCount.value, 99))

  async function fetchList() {
    try {
      const res = await notificationsApi.listMine({ page: 1, page_size: 50 })
      list.value = res.items || []
      return list.value
    } catch (_) {
      list.value = []
      return []
    }
  }

  async function fetchUnreadCount() {
    try {
      const res = await notificationsApi.getUnreadCount()
      unreadCount.value = res.count ?? 0
      return unreadCount.value
    } catch (_) {
      unreadCount.value = 0
      return 0
    }
  }

  async function markRead(id) {
    try {
      await notificationsApi.markRead(id)
      const item = list.value.find((n) => n.id === id)
      if (item) item.read = true
      await fetchUnreadCount()
    } catch (_) {}
  }

  async function markAllRead() {
    try {
      await notificationsApi.markAllRead()
      list.value.forEach((n) => { n.read = true })
      unreadCount.value = 0
    } catch (_) {}
  }

  async function refresh() {
    await Promise.all([fetchList(), fetchUnreadCount()])
  }

  return {
    list,
    unreadCount,
    unreadCountDisplay,
    fetchList,
    fetchUnreadCount,
    markRead,
    markAllRead,
    refresh
  }
})
