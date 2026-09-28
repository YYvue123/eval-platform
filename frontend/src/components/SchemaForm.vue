<template>
  <el-form label-width="120px" size="small" @submit.prevent>
    <el-form-item
      v-for="field in fields"
      :key="field.key"
      :label="field.label"
      :required="field.required"
    >
      <el-input
        v-if="field.kind === 'string'"
        :model-value="modelValue[field.key]"
        :placeholder="field.placeholder"
        @update:model-value="set(field.key, $event)"
      />
      <el-input-number
        v-else-if="field.kind === 'number'"
        :model-value="modelValue[field.key]"
        style="width: 100%"
        @update:model-value="set(field.key, $event)"
      />
      <el-switch
        v-else-if="field.kind === 'boolean'"
        :model-value="!!modelValue[field.key]"
        @update:model-value="set(field.key, $event)"
      />
      <el-select
        v-else-if="field.kind === 'enum'"
        :model-value="modelValue[field.key]"
        style="width: 100%"
        clearable
        @update:model-value="set(field.key, $event)"
      >
        <el-option v-for="opt in field.enum" :key="opt" :label="String(opt)" :value="opt" />
      </el-select>
      <el-input
        v-else
        type="textarea"
        :rows="3"
        :model-value="stringifyComplex(modelValue[field.key])"
        :placeholder="field.placeholder || 'JSON'"
        @update:model-value="setComplex(field.key, $event)"
      />
      <div v-if="field.description" class="hint">{{ field.description }}</div>
    </el-form-item>
    <el-alert v-if="!fields.length" type="info" :closable="false" title="无 Schema 字段，请使用高级 JSON" />
  </el-form>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  schema: { type: Object, default: () => ({}) },
  modelValue: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue'])

const fields = computed(() => {
  const schema = props.schema || {}
  const propsMap = schema.properties || {}
  const required = new Set(schema.required || [])
  return Object.entries(propsMap).map(([key, def]) => {
    const d = def || {}
    let kind = d.type || 'string'
    if (d.enum) kind = 'enum'
    if (kind === 'integer') kind = 'number'
    if (kind === 'array' || kind === 'object') kind = 'complex'
    return {
      key,
      label: d.title || key,
      description: d.description || '',
      required: required.has(key),
      kind,
      enum: d.enum || [],
      placeholder: d.default != null ? String(d.default) : '',
    }
  })
})

function set(key, val) {
  emit('update:modelValue', { ...props.modelValue, [key]: val })
}

function stringifyComplex(v) {
  if (v == null || v === '') return ''
  if (typeof v === 'string') return v
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

function setComplex(key, text) {
  const raw = (text || '').trim()
  if (!raw) {
    set(key, undefined)
    return
  }
  try {
    set(key, JSON.parse(raw))
  } catch {
    set(key, raw)
  }
}

defineExpose({
  validate() {
    const missing = fields.value.filter((f) => f.required && (props.modelValue[f.key] === undefined || props.modelValue[f.key] === '' || props.modelValue[f.key] === null))
    return { ok: !missing.length, missing: missing.map((m) => m.key) }
  },
})
</script>

<style scoped>
.hint { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }
</style>
