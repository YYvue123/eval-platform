<template>
  <el-dropdown trigger="click" placement="bottom-end" @visible-change="onVisibleChange">
    <el-badge :value="store.unreadCountDisplay" :hidden="store.unreadCount === 0" type="danger" class="notification-badge">
      <el-button :icon="Bell" circle />
    </el-badge>
    <template #dropdown>
      <div class="notification-dropdown">
        <div class="notification-header">
          <span>通知中心</span>
          <el-button v-if="store.unreadCount > 0" link type="primary" size="small" @click="handleMarkAllRead">
            全部已读
          </el-button>
        </div>
        <div class="notification-list">
          <el-empty v-if="!store.list.length" description="暂无通知" :image-size="60" />
          <div
            v-for="item in store.list"
            :key="item.id"
            class="notification-item"
            :class="[item.type, { unread: !item.read }]"
            @click="handleItemClick(item)"
          >
            <el-icon class="item-icon">
              <CircleCheck v-if="item.type === 'success'" />
              <CircleClose v-else-if="item.type === 'error'" />
              <Warning v-else-if="item.type === 'warning'" />
              <InfoFilled v-else />
            </el-icon>
            <div class="item-content">
              <div class="item-title">{{ item.title }}</div>
              <div v-if="item.message" class="item-message">{{ item.message }}</div>
              <div class="item-time">{{ item.created_at ? formatTime(item.created_at) : '' }}</div>
            </div>
            <span v-if="!item.read" class="unread-dot" />
          </div>
        </div>
      </div>
    </template>
  </el-dropdown>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { Bell, CircleCheck, CircleClose, Warning, InfoFilled } from '@element-plus/icons-vue'
import { useNotificationStore } from '@/stores/notification'

const store = useNotificationStore()

function formatTime(s) {
  if (!s) return ''
  const d = new Date(s)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  if (sameDay) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function onVisibleChange(visible) {
  if (visible) {
    await store.fetchList()
  }
}

async function handleItemClick(item) {
  if (!item.read) {
    await store.markRead(item.id)
  }
}

async function handleMarkAllRead() {
  await store.markAllRead()
}

let pollTimer = null
onMounted(() => {
  store.fetchUnreadCount()
  pollTimer = setInterval(() => store.fetchUnreadCount(), 60000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.notification-badge {
  margin-right: 8px;
}
.notification-badge :deep(.el-badge__content) {
  background-color: #f56c6c;
}
.notification-dropdown {
  width: 340px;
  max-height: 420px;
  padding: 0;
}
.notification-header {
  padding: 12px 16px;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
.notification-list {
  max-height: 340px;
  overflow-y: auto;
  padding: 8px 0;
}
.notification-item {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  position: relative;
}
.notification-item:hover {
  background: #f5f7fa;
}
.notification-item:last-child {
  border-bottom: none;
}
.notification-item.unread {
  background: #ecf5ff;
}
.notification-item.unread:hover {
  background: #d9ecff;
}
.notification-item.success .item-icon { color: #67c23a; }
.notification-item.error .item-icon { color: #f56c6c; }
.notification-item.warning .item-icon { color: #e6a23c; }
.notification-item.info .item-icon { color: #909399; }
.item-content { flex: 1; min-width: 0; }
.item-title { font-size: 14px; font-weight: 500; }
.item-message { font-size: 12px; color: #606266; margin-top: 4px; white-space: pre-wrap; word-break: break-word; }
.item-time { font-size: 11px; color: #909399; margin-top: 4px; }
.unread-dot {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f56c6c;
}
</style>
