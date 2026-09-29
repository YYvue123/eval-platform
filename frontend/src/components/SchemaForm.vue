<template>
  <el-form label-width="120px" size="small" @submit.prevent>
    <el-form-item
      v-for="field in fields"
      :key="field.key"
      :label="field.label"
      :required="field.required"
    >
      <el-input
        v-if="field.kind === 'string' && !field.advanced"
        :model-value="modelValue[field.key]"
        :placeholder="field.placeholder"
        @update:model-value="set(field.key, $event)"
      />
      <el-input-number
        v-else-if="field.kind === 'integer'"
        :model-value="modelValue[field.key]"
        style="width: 100%"
        :step="1"
        :precision="0"
        :min="field.minimum"
        :max="field.maximum"
        @update:model-value="set(field.key, $event)"
      />
      <el-input-number
        v-else-if="field.kind === 'number'"
        :model-value="modelValue[field.key]"
        style="width: 100%"
        :min="field.minimum"
        :max="field.maximum"
        @update:model-value="set(field.key, $event)"
      />
      <el-switch
        v-else-if="field.kind === 'boolean'"
        :model-value="!!modelValue[field.key]"
        @update:model-value="set(field.key, $event)"
      />
      <el-select
        v-else-if="field.kind === 'enum' && !field.advanced"
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
        :model-value="drafts[field.key]"
        :placeholder="field.placeholder || 'JSON'"
        @update:model-value="setComplex(field, $event)"
      />
      <div v-if="boundHint(field)" class="hint">{{ boundHint(field) }}</div>
      <div v-if="field.description" class="hint">{{ field.description }}</div>
      <div v-if="fieldErrors[field.key]" class="field-error" role="alert">{{ fieldErrors[field.key] }}</div>
    </el-form-item>
    <el-alert v-if="!fields.length" type="info" :closable="false" title="无 Schema 字段，请使用高级 JSON" />
  </el-form>
</template>

<script setup>
import { computed, reactive, watch } from 'vue'
import {
  applyDefaults,
  buildFields,
  collectValidation,
  isComplexField,
  jsonErrorMessage,
  stringifyComplex,
  validateValue,
} from '@/utils/schemaForm.js'

const props = defineProps({
  schema: { type: Object, default: () => ({}) },
  modelValue: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue'])

const drafts = reactive({})
const fieldErrors = reactive({})
const draftErrors = reactive({})

const fields = computed(() => buildFields(props.schema).map((field) => ({
  ...field,
  placeholder: field.default != null ? String(field.default) : '',
})))

function clearFieldError(key) {
  delete fieldErrors[key]
  delete draftErrors[key]
}

function set(key, val) {
  clearFieldError(key)
  emit('update:modelValue', { ...props.modelValue, [key]: val })
}

function setComplex(field, text) {
  drafts[field.key] = text
  if (!String(text || '').trim()) {
    clearFieldError(field.key)
    set(field.key, undefined)
    return
  }
  try {
    const parsed = JSON.parse(text)
    const error = validateValue(field.definition, parsed)
    if (error) {
      fieldErrors[field.key] = error
      draftErrors[field.key] = error
      return
    }
    clearFieldError(field.key)
    set(field.key, parsed)
  } catch (error) {
    const message = jsonErrorMessage(error, text)
    fieldErrors[field.key] = message
    draftErrors[field.key] = message
  }
}

function boundHint(field) {
  if (field.kind !== 'integer' && field.kind !== 'number') return ''
  const parts = []
  if (field.minimum != null) parts.push(`最小 ${field.minimum}`)
  if (field.maximum != null) parts.push(`最大 ${field.maximum}`)
  if (field.exclusiveMinimum != null) parts.push(`大于 ${field.exclusiveMinimum}`)
  if (field.exclusiveMaximum != null) parts.push(`小于 ${field.exclusiveMaximum}`)
  return parts.join('，')
}

function valuesEqual(a, b) {
  try {
    return JSON.stringify(a) === JSON.stringify(b)
  } catch {
    return a === b
  }
}

watch(
  () => [props.schema, props.modelValue],
  () => {
    const next = applyDefaults(props.schema, props.modelValue)
    if (!valuesEqual(next, props.modelValue)) emit('update:modelValue', next)
  },
  { deep: true, immediate: true },
)

watch(
  () => [props.schema, props.modelValue],
  () => {
    for (const field of fields.value) {
      if (!isComplexField(field) && field.kind !== 'object' && field.kind !== 'array') continue
      if (fieldErrors[field.key]) continue
      drafts[field.key] = stringifyComplex(props.modelValue[field.key])
    }
  },
  { deep: true, immediate: true },
)

defineExpose({
  validate() {
    const result = collectValidation(fields.value, props.modelValue, draftErrors)
    for (const key of Object.keys(fieldErrors)) {
      if (!Object.prototype.hasOwnProperty.call(result.errors, key)) delete fieldErrors[key]
    }
    Object.assign(fieldErrors, result.errors)
    return result
  },
})
</script>

<style scoped>
.hint { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }
.field-error { font-size: 12px; color: var(--el-color-danger); margin-top: 4px; }
</style>
