<template>
  <span class="status-badge" :class="tone">{{ label }}</span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  phase: { type: String, default: 'idle' },
  text: { type: String, default: '' },
})

const MAP = {
  idle: { label: '尚未开始', tone: 'neutral' },
  planning: { label: '正在规划', tone: 'info' },
  needs_input: { label: '待补充', tone: 'warning' },
  awaiting_approval: { label: '待审批', tone: 'warning' },
  approved: { label: '已审批', tone: 'success' },
  running: { label: '执行中', tone: 'info' },
  budget_paused: { label: '预算暂停', tone: 'warning' },
  failed: { label: '执行失败', tone: 'danger' },
  completed: { label: '已完成', tone: 'success' },
}

const label = computed(() => props.text || MAP[props.phase]?.label || props.phase)
const tone = computed(() => MAP[props.phase]?.tone || 'neutral')
</script>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: var(--radius-sm, 6px);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.6;
  border: 1px solid transparent;
}
.neutral { color: var(--text-secondary, #64748b); background: #f1f5f9; border-color: #e2e8f0; }
.info { color: #1d4ed8; background: #eff6ff; border-color: #bfdbfe; }
.warning { color: #b45309; background: #fffbeb; border-color: #fde68a; }
.success { color: #15803d; background: #f0fdf4; border-color: #bbf7d0; }
.danger { color: #b91c1c; background: #fef2f2; border-color: #fecaca; }
:global(.dark) .neutral { background: #334155; color: #cbd5e1; border-color: #475569; }
</style>
