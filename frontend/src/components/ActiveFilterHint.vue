<template>
  <div v-if="visible && items.length" class="active-filter-hint">
    <span class="count">已生效 {{ items.length }} 个筛选条件</span>
    <el-tag
      v-for="item in items"
      :key="item.key"
      size="small"
      closable
      @close="$emit('remove', item.key)"
    >
      {{ item.label }}：{{ item.text }}
    </el-tag>
    <el-button link type="primary" @click="$emit('clear')">清空筛选</el-button>
  </div>
</template>

<script setup>
defineProps({
  visible: { type: Boolean, default: false },
  items: { type: Array, default: () => [] }
})

defineEmits(['remove', 'clear'])
</script>

<style scoped>
.active-filter-hint {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}
.count {
  font-weight: 500;
  color: var(--text-primary);
}
</style>
