<template>
  <el-select
    :model-value="modelValue"
    filterable
    remote
    clearable
    reserve-keyword
    :remote-method="search"
    :loading="loading"
    :placeholder="placeholder"
    :disabled="disabled"
    style="width: 100%"
    @update:model-value="onChange"
    @visible-change="(v) => v && ensureLoaded()"
  >
    <el-option
      v-for="opt in options"
      :key="opt.id"
      :label="opt.label"
      :value="opt.id"
      :disabled="opt.disabled"
    >
      <div class="opt">
        <span>{{ opt.label }}</span>
        <span v-if="opt.hint" class="hint">{{ opt.hint }}</span>
      </div>
    </el-option>
  </el-select>
</template>

<script setup>
import { ref, watch } from 'vue'
import { datasetsApi, modelsApi } from '@/api'

const props = defineProps({
  modelValue: { type: [Number, String, null], default: null },
  kind: { type: String, required: true }, // dataset | model
  placeholder: { type: String, default: '搜索并选择' },
  disabled: { type: Boolean, default: false },
  /** 仅展示可调用模型（有 api_url） */
  requireApiUrl: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'select'])

const loading = ref(false)
const options = ref([])
let loadedOnce = false

function mapDataset(d) {
  const status = d.status || d.publish_status || ''
  const disabled = ['draft', 'rejected', 'deleted'].includes(status) && status !== 'published' && status !== 'approved'
  // 允许大多数非 deleted；给出提示
  const unusable = status === 'deleted'
  return {
    id: d.id,
    label: `#${d.id} ${d.name || '未命名'}`,
    hint: [status, d.domain_type || d.scene].filter(Boolean).join(' · '),
    disabled: unusable,
    raw: d,
  }
}

function mapModel(m) {
  const hasUrl = !!(m.api_url || '').trim()
  const disabled = props.requireApiUrl ? !hasUrl : m.status === 'deleted'
  return {
    id: m.id,
    label: `#${m.id} ${m.name || '未命名'}`,
    hint: [m.provider, hasUrl ? '已配置连接' : '未配置 api_url', m.health_status || m.status]
      .filter(Boolean)
      .join(' · '),
    disabled,
    raw: m,
  }
}

async function search(q = '') {
  loading.value = true
  try {
    if (props.kind === 'dataset') {
      const res = await datasetsApi.list({ page: 1, page_size: 30, search: q || undefined })
      options.value = (res.items || []).map(mapDataset)
    } else {
      const res = await modelsApi.list({ page: 1, page_size: 30, search: q || undefined })
      options.value = (res.items || []).map(mapModel)
    }
    // 保证当前值出现在选项中
    if (props.modelValue && !options.value.some((o) => o.id === props.modelValue)) {
      await hydrateCurrent()
    }
  } finally {
    loading.value = false
  }
}

async function hydrateCurrent() {
  if (!props.modelValue) return
  try {
    if (props.kind === 'dataset') {
      const d = await datasetsApi.get(props.modelValue)
      options.value = [mapDataset(d), ...options.value.filter((o) => o.id !== d.id)]
    } else {
      const m = await modelsApi.get(props.modelValue)
      options.value = [mapModel(m), ...options.value.filter((o) => o.id !== m.id)]
    }
  } catch {
    /* ignore missing */
  }
}

async function ensureLoaded() {
  if (loadedOnce && options.value.length) return
  loadedOnce = true
  await search('')
}

function onChange(v) {
  emit('update:modelValue', v || null)
  const hit = options.value.find((o) => o.id === v)
  emit('select', hit || null)
}

watch(
  () => props.modelValue,
  (v) => {
    if (v && !options.value.some((o) => o.id === v)) hydrateCurrent()
  },
  { immediate: true },
)
</script>

<style scoped>
.opt { display: flex; justify-content: space-between; gap: 12px; width: 100%; }
.hint { color: var(--el-text-color-secondary); font-size: 12px; }
</style>
