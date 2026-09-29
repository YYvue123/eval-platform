<template>
  <div v-if="state === 'success'" class="page-async-state">
    <slot />
  </div>
  <div v-else class="page-async-state page-async-state--status">
    <StatusBadge :phase="badgePhase" :text="copy.title" />
    <p class="page-async-state__title">{{ copy.title }}</p>
    <p v-if="copy.next" class="page-async-state__next">{{ copy.next }}</p>
    <p v-if="errorMessage" class="page-async-state__error">{{ errorMessage }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { ASYNC_STATE_COPY } from '@/utils/asyncState.js'

const props = defineProps({
  state: { type: String, required: true },
  errorMessage: { type: String, default: '' },
})

const PHASE = {
  loading: 'running',
  error: 'failed',
  forbidden: 'blocked',
  empty: 'idle',
  uncreated: 'idle',
}

const copy = computed(() => ASYNC_STATE_COPY[props.state] || ASYNC_STATE_COPY.loading)
const badgePhase = computed(() => PHASE[props.state] || 'idle')
</script>

<style scoped>
.page-async-state--status {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 24px 8px;
}
.page-async-state__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}
.page-async-state__next,
.page-async-state__error {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.5;
}
</style>
