export function buildFields(schema) {
  const root = schema || {}
  const propsMap = root.properties || {}
  const required = new Set(root.required || [])
  return Object.entries(propsMap).map(([key, definition]) => {
    const def = definition || {}
    let kind = def.type || 'string'
    if (Array.isArray(def.enum) && def.enum.length) kind = 'enum'
    const advanced = Boolean(
      def.$ref || def.oneOf || def.anyOf || def.allOf ||
      (def.type === 'object' && def.properties),
    )
    return {
      key,
      label: def.title || key,
      description: def.description || '',
      required: required.has(key),
      kind,
      definition: def,
      enum: def.enum || [],
      default: def.default,
      minimum: def.minimum,
      maximum: def.maximum,
      exclusiveMinimum: def.exclusiveMinimum,
      exclusiveMaximum: def.exclusiveMaximum,
      minLength: def.minLength,
      maxLength: def.maxLength,
      pattern: def.pattern,
      format: def.format,
      advanced,
    }
  })
}

export function applyDefaults(schema, value) {
  const propsMap = (schema && schema.properties) || {}
  const next = { ...(value || {}) }
  for (const [key, definition] of Object.entries(propsMap)) {
    if (next[key] !== undefined) continue
    const def = definition || {}
    if (Object.prototype.hasOwnProperty.call(def, 'default')) {
      next[key] = def.default
    }
  }
  return next
}

function boundMessage(definition, value) {
  if (typeof value !== 'number') return ''
  if (definition.minimum != null && value < definition.minimum) {
    return `不能小于 ${definition.minimum}`
  }
  if (definition.maximum != null && value > definition.maximum) {
    return `不能大于 ${definition.maximum}`
  }
  if (definition.exclusiveMinimum != null && value <= definition.exclusiveMinimum) {
    return `必须大于 ${definition.exclusiveMinimum}`
  }
  if (definition.exclusiveMaximum != null && value >= definition.exclusiveMaximum) {
    return `必须小于 ${definition.exclusiveMaximum}`
  }
  return ''
}

function isValidUri(value) {
  try {
    const url = new URL(value)
    return Boolean(url.protocol && url.host)
  } catch {
    return false
  }
}

export function validateValue(definition, value) {
  if (!definition || value === undefined || value === null || value === '') return ''
  const type = definition.type

  if (type === 'integer') {
    if (!Number.isInteger(value)) return '必须是整数'
    const bound = boundMessage(definition, value)
    if (bound) return bound
  } else if (type === 'number') {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '必须是数字'
    const bound = boundMessage(definition, value)
    if (bound) return bound
  } else if (type === 'string') {
    if (typeof value !== 'string') return '必须是字符串'
    if (definition.minLength != null && value.length < definition.minLength) return '长度不足'
    if (definition.maxLength != null && value.length > definition.maxLength) return '长度超出'
    if (definition.pattern) {
      try {
        if (!new RegExp(definition.pattern).test(value)) return '格式不符合要求'
      } catch {
        return '格式不符合要求'
      }
    }
    if (definition.format === 'uri' && !isValidUri(value)) return '必须是有效 URL'
    if (definition.format === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
      return '必须是有效邮箱'
    }
    if (definition.format === 'date') {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || Number.isNaN(Date.parse(`${value}T00:00:00`))) {
        return '必须是有效日期'
      }
    }
  } else if (type === 'array') {
    if (!Array.isArray(value)) return '必须是数组'
  } else if (type === 'object') {
    if (typeof value !== 'object' || Array.isArray(value)) return '必须是对象'
  } else if (type === 'boolean') {
    if (typeof value !== 'boolean') return '必须是布尔值'
  }

  if (Array.isArray(definition.enum) && definition.enum.length && !definition.enum.includes(value)) {
    return '不在允许的选项中'
  }
  return ''
}

export function jsonErrorMessage(error, text) {
  const message = error && error.message ? error.message : String(error)
  const match = String(message).match(/position\s+(\d+)/i)
  if (match) {
    const pos = Number(match[1])
    const line = String(text || '').slice(0, pos).split('\n').length
    return `JSON 无效: ${message} (第 ${line} 行)`
  }
  return `JSON 无效: ${message}`
}

export function stringifyComplex(value) {
  if (value == null || value === '') return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

export function isComplexField(field) {
  return Boolean(
    field.advanced ||
    field.kind === 'object' ||
    field.kind === 'array' ||
    field.kind === 'complex',
  )
}

function isEmptyValue(value) {
  return value === undefined || value === null || value === ''
}

/** Rebuild errors from current values. Keep draftErrors only for complex fields that never called set(). */
export function collectValidation(fields, values, draftErrors = {}) {
  const errors = {}
  const missing = []
  const valueMap = values || {}
  for (const field of fields || []) {
    const value = valueMap[field.key]
    const draftError = isComplexField(field) ? draftErrors[field.key] : undefined
    if (draftError) {
      errors[field.key] = draftError
    }
    if (field.required && isEmptyValue(value)) {
      missing.push(field.key)
      if (!errors[field.key]) errors[field.key] = '必填'
      continue
    }
    if (draftError) continue
    const message = validateValue(field.definition, value)
    if (message) errors[field.key] = message
  }
  return {
    ok: missing.length === 0 && Object.keys(errors).length === 0,
    missing,
    errors,
  }
}
