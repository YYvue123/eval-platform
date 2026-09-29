<template>
  <div class="resource-picker">
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
      <el-option
        v-if="canLoadMore"
        key="__more__"
        label="加载更多"
        value="__more__"
        :disabled="false"
      />
    </el-select>
    <p v-if="loadError" class="picker-error">{{ loadError }}</p>
  </div>
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
const loadError = ref('')
const options = ref([])
const page = ref(1)
const pageSize = 30
const lastQuery = ref('')
const lastFetchCount = ref(0)
const catalogTotal = ref(0)
let loadedOnce = false

const canLoadMore = ref(false)

function mapDataset(d) {
  const status = d.status || d.publish_status || ''
  const disabled = ['draft', 'rejected', 'deleted'].includes(status) && status !== 'published' && status !== 'approved'
  // 允许大多数非 deleted；给出提示
  const unusable = status === 'deleted'
  return {
    id: d.id,
    label: d.name || '未命名数据集',
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
    label: m.name || '未命名模型',
    hint: [m.provider, hasUrl ? '已配置连接' : '未配置 api_url', m.health_status || m.status]
      .filter(Boolean)
      .join(' · '),
    disabled,
    raw: m,
  }
}

function mapper() {
  return props.kind === 'dataset' ? mapDataset : mapModel
}

function updateCanLoadMore(res, mergedLength) {
  const batch = res.items || []
  lastFetchCount.value = batch.length
  catalogTotal.value = res.total || 0
  canLoadMore.value = catalogTotal.value > mergedLength || batch.length === pageSize
}

async function fetchPage(q, nextPage, replace) {
  loading.value = true
  loadError.value = ''
  try {
    const api = props.kind === 'dataset' ? datasetsApi : modelsApi
    const res = await api.list({ page: nextPage, page_size: pageSize, search: q || undefined })
    const mapped = (res.items || []).map(mapper())
    if (replace) {
      options.value = mapped
    } else {
      const seen = new Set(options.value.map((o) => o.id))
      for (const o of mapped) {
        if (!seen.has(o.id)) {
          options.value.push(o)
          seen.add(o.id)
        }
      }
    }
    page.value = nextPage
    updateCanLoadMore(res, options.value.length)
    if (props.modelValue && !options.value.some((o) => o.id === props.modelValue)) {
      await hydrateCurrent()
    }
  } catch (e) {
    const d = e?.response?.data
    const msg = d?.message || d?.detail || e?.message
    loadError.value = typeof msg === 'string' && msg ? msg : '资源列表加载失败'
  } finally {
    loading.value = false
  }
}

async function search(q = '') {
  lastQuery.value = q
  page.value = 1
  await fetchPage(q, 1, true)
}

async function loadMore() {
  await fetchPage(lastQuery.value, page.value + 1, false)
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
  if (v === '__more__') {
    loadMore()
    return
  }
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
.picker-error { margin: 6px 0 0; font-size: 12px; color: var(--el-color-danger); line-height: 1.4; }
</style>
