export const ADVANCED_SCHEMA_HINT = '高级 Schema 已保留，字段表不支持无损编辑'

export const DEFAULT_SKILL_INPUTS = {
  s1: JSON.stringify({ text: { $ref: '$input.text' } }),
  s2: JSON.stringify({
    values: { $ref: 's1.output.values' },
    target_unit: { $ref: '$input.target_unit' },
  }),
}

const STEP_REF = /^(?:step_(\d+)|([A-Za-z_][\w-]*))(?:\.(.+))?$/
const SIMPLE_TYPES = new Set(['string', 'number', 'integer', 'boolean'])
const ADVANCED_KEYS = new Set([
  'enum',
  'description',
  'minimum',
  'maximum',
  'exclusiveMinimum',
  'exclusiveMaximum',
  'minLength',
  'maxLength',
  'pattern',
  'format',
  'oneOf',
  'anyOf',
  'allOf',
  '$ref',
  'items',
  'properties',
  'additionalProperties',
])

export function emptyWizard() {
  return {
    kind: 'tool',
    ns: 'demo',
    slug: '',
    name: '',
    description: '',
    version: '1.0.0',
    call_mode: 'sync',
    idempotent: true,
    endpoint: '',
    method: 'POST',
    timeout: 30,
    credentialRef: '',
    token: '',
    mcpTransport: 'streamable_http',
    commandAlias: '',
    skillSteps: [
      { step_id: 's1', resource_id: '', inputJson: DEFAULT_SKILL_INPUTS.s1 },
      { step_id: 's2', resource_id: '', inputJson: DEFAULT_SKILL_INPUTS.s2 },
    ],
    skillExecution: 'workflow',
    skillEntry: '',
    editing: false,
    allowlist: '',
    paramMode: 'form',
    fields: [
      { key: 'prediction', type: 'string', required: true },
      { key: 'reference', type: 'string', required: true },
    ],
    schemaJson: '',
    schemaAdvancedKept: false,
    rawManifest: '',
  }
}

export function emptySkillStep(index) {
  const n = Number(index) || 1
  return {
    step_id: `s${n}`,
    resource_id: '',
    inputJson: n === 1 ? DEFAULT_SKILL_INPUTS.s1 : n === 2 ? DEFAULT_SKILL_INPUTS.s2 : '{}',
  }
}

export function isHttpUrl(value) {
  return /^https?:\/\//.test(String(value || '').trim())
}

export function parseInputJson(text, original) {
  const kept = original == null ? String(text ?? '') : String(original)
  try {
    const value = JSON.parse(text || '{}')
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return { ok: false, value: null, error: '步骤输入必须是 JSON 对象', kept }
    }
    return { ok: true, value, error: '', kept }
  } catch (error) {
    return { ok: false, value: null, error: `JSON 无效：${error.message}`, kept }
  }
}

function collectRefs(node, acc = []) {
  if (Array.isArray(node)) {
    node.forEach((item) => collectRefs(item, acc))
    return acc
  }
  if (!node || typeof node !== 'object') return acc
  if (typeof node.$ref === 'string') acc.push(node.$ref)
  Object.values(node).forEach((item) => collectRefs(item, acc))
  return acc
}

function knownStepIds(steps, beforeIndex) {
  return new Set(
    steps.slice(0, beforeIndex).map((step) => String(step.step_id || '').trim()).filter(Boolean),
  )
}

export function validateRef(ref, previousIds) {
  const value = String(ref || '')
  if (value.startsWith('$input.') || value === '$input') return ''
  if (value.startsWith('$global.')) return ''
  const match = STEP_REF.exec(value)
  if (!match) return `无法解析引用 ${value}`
  const sid = match[2]
  if (match[1] != null) return ''
  if (sid && !previousIds.has(sid)) return `未知步骤引用：${value}`
  return ''
}

export function validateSkillSteps(steps, allowedToolIds) {
  const list = Array.isArray(steps) ? steps : []
  const errors = []
  const chain = []
  if (!list.length) {
    return { ok: false, errors: ['Skill 至少需要一个步骤'], chain }
  }
  const ids = list.map((step) => String(step.step_id || '').trim())
  if (ids.some((id) => !id)) errors.push('每个步骤都需要 step_id')
  if (new Set(ids.filter(Boolean)).size !== ids.filter(Boolean).length) {
    errors.push('step_id 必须唯一')
  }
  list.forEach((step, index) => {
    const sid = String(step.step_id || `s${index + 1}`)
    const rid = String(step.resource_id || '').trim()
    if (!rid) errors.push(`步骤 ${sid} 必须选择工具`)
    else if (allowedToolIds && allowedToolIds.size && !allowedToolIds.has(rid)) {
      errors.push(`步骤 ${sid} 只能选择列表中的工具`)
    }
    const parsed = parseInputJson(step.inputJson, step.inputJson)
    if (!parsed.ok) errors.push(`步骤 ${sid}：${parsed.error}`)
    else {
      const prev = knownStepIds(list, index)
      for (const ref of collectRefs(parsed.value)) {
        const msg = validateRef(ref, prev)
        if (msg) errors.push(`步骤 ${sid}：${msg}`)
      }
      chain.push({
        step_id: sid,
        resource_id: rid,
        input: parsed.value,
      })
    }
  })
  return { ok: errors.length === 0, errors, chain }
}

export function skillCheckNotes(steps) {
  const result = validateSkillSteps(steps, null)
  if (result.ok) {
    return {
      ok: true,
      message: '引用检查：通过（未执行真实调用，注册后在试用台验证）',
    }
  }
  return {
    ok: false,
    message: `引用检查失败：${result.errors.join('；')}`,
  }
}

export function validateWizardConnect(wizard) {
  if (wizard.kind === 'tool') {
    if (!isHttpUrl(wizard.endpoint)) return { ok: false, message: '工具需要 http(s) 地址' }
    return { ok: true, message: '' }
  }
  if (wizard.kind === 'mcp') {
    if (wizard.mcpTransport === 'stdio') {
      const aliases = wizard.stdioAliases || []
      if (!aliases.length) {
        return { ok: false, message: '服务端未配置允许的 stdio 服务，请联系管理员配置' }
      }
      if (!aliases.includes(wizard.commandAlias)) {
        return { ok: false, message: '请选择服务端允许的 stdio 别名' }
      }
      return { ok: true, message: '' }
    }
    if (!isHttpUrl(wizard.endpoint)) return { ok: false, message: 'MCP 需要 http(s) 地址' }
    return { ok: true, message: '' }
  }
  if (wizard.kind === 'skill') {
    const execution = wizard.skillExecution || 'workflow'
    if (execution !== 'workflow') {
      if (!String(wizard.skillEntry || '').trim()) return { ok: false, message: '请填写执行入口' }
      return { ok: true, message: '', errors: [] }
    }
    const result = validateSkillSteps(wizard.skillSteps, wizard.allowedToolIds)
    if (!result.ok) return { ok: false, message: result.errors[0] || 'Skill 配置不完整', errors: result.errors }
    return { ok: true, message: '', errors: [] }
  }
  return { ok: true, message: '' }
}

function splitAllowlist(text) {
  return String(text || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function buildMcpInterfaces(wizard) {
  if (wizard.mcpTransport === 'stdio') {
    return { transport: 'stdio', command_alias: wizard.commandAlias }
  }
  const interfaces = {
    transport: 'streamable_http',
    endpoint: wizard.endpoint,
    method: 'POST',
    auth_type: wizard.credentialRef ? 'bearer' : 'none',
  }
  if (wizard.credentialRef) interfaces.auth = { credential_ref: wizard.credentialRef }
  const allow = splitAllowlist(wizard.allowlist)
  if (allow.length) interfaces.egress_allowlist = allow
  return interfaces
}

export function schemaFromFields(fields) {
  const properties = {}
  const required = []
  for (const field of fields || []) {
    if (!field.key) continue
    properties[field.key] = { type: field.type || 'string' }
    if (field.required) required.push(field.key)
  }
  return { type: 'object', properties, required }
}

function propertyIsAdvanced(def) {
  if (!def || typeof def !== 'object') return true
  if (!SIMPLE_TYPES.has(def.type)) return true
  if (def.type === 'object' || def.type === 'array') return true
  return Object.keys(def).some((key) => {
    if (key === 'type') return false
    return ADVANCED_KEYS.has(key)
  })
}

export function schemaIsSimpleForm(schema) {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) return false
  const props = schema.properties
  if (!props || typeof props !== 'object') return false
  return Object.values(props).every((def) => !propertyIsAdvanced(def))
}

export function schemaFormSync(schemaJson, currentFields) {
  const text = String(schemaJson || '').trim()
  if (!text) {
    return { advancedKept: false, fields: currentFields || [], hint: '', error: '' }
  }
  let schema
  try {
    schema = JSON.parse(text)
  } catch (error) {
    return {
      advancedKept: true,
      fields: currentFields || [],
      hint: ADVANCED_SCHEMA_HINT,
      error: `JSON 无效：${error.message}`,
    }
  }
  if (!schemaIsSimpleForm(schema)) {
    return {
      advancedKept: true,
      fields: currentFields || [],
      hint: ADVANCED_SCHEMA_HINT,
      error: '',
    }
  }
  const required = schema.required || []
  const fields = Object.entries(schema.properties || {}).map(([key, def]) => ({
    key,
    type: def.type || 'string',
    required: required.includes(key),
  }))
  return { advancedKept: false, fields, hint: '', error: '' }
}

export const INVOCABLE_TOOL_STATUSES = ['online', 'pending', 'registered']

export function isInvocableTool(row) {
  return INVOCABLE_TOOL_STATUSES.includes(String(row?.status || ''))
}

export function mergeToolPages(existing, page) {
  const map = new Map()
  for (const item of existing || []) {
    if (item?.resource_id) map.set(item.resource_id, item)
  }
  for (const item of page.items || []) {
    if (item?.resource_id) map.set(item.resource_id, item)
  }
  const items = [...map.values()]
  const pageNum = Number(page.page) || 1
  const total = Number(page.total) || items.length
  return { items, hasMore: items.length < total, nextPage: pageNum + 1, total }
}

export function toolOptionLabel(item) {
  if (!item) return ''
  return [item.name, item.resource_id, item.version, item.health_status || item.status]
    .filter(Boolean)
    .join(' · ')
}

function pretty(value) {
  try {
    return JSON.stringify(value ?? {}, null, 2)
  } catch {
    return String(value)
  }
}

export function buildManifest(wizard) {
  if (String(wizard.rawManifest || '').trim()) {
    return JSON.parse(wizard.rawManifest)
  }
  const rid = `${wizard.ns}/${wizard.slug}`.toLowerCase()
  if (wizard.kind === 'mcp') {
    return {
      spec_version: '0.6.1',
      resource_id: rid,
      resource_type: 'mcp',
      name: wizard.name,
      description: wizard.description,
      version: wizard.version,
      owner: { name: 'tenant', contact: 'n/a', email: 'n/a@local' },
      capabilities: {
        input_schema: { type: 'object', properties: { method: { type: 'string' }, params: { type: 'object' } } },
        output_schema: { type: 'object' },
        call_mode: 'sync',
        idempotent: wizard.idempotent === true,
        timeout: Number(wizard.timeout) || 30,
      },
      interfaces: buildMcpInterfaces(wizard),
    }
  }
  const schema = wizard.schemaAdvancedKept && String(wizard.schemaJson || '').trim()
    ? JSON.parse(wizard.schemaJson)
    : wizard.paramMode === 'json' && String(wizard.schemaJson || '').trim()
      ? JSON.parse(wizard.schemaJson)
      : schemaFromFields(wizard.fields)
  const base = {
    spec_version: '0.6.1',
    resource_id: rid,
    resource_type: wizard.kind,
    name: wizard.name,
    description: wizard.description,
    version: wizard.version,
    owner: { name: 'tenant', contact: 'n/a', email: 'n/a@local' },
    capabilities: {
      input_schema: schema,
      output_schema: { type: 'object' },
      call_mode: wizard.call_mode,
      idempotent: wizard.idempotent === true,
      timeout: Number(wizard.timeout) || 30,
      side_effects: 'none',
    },
  }
  if (wizard.kind === 'skill') {
    const execution = wizard.skillExecution || 'workflow'
    base.skill = {
      execution_type: execution,
      entry_point: wizard.skillEntry || '',
      chainable: execution === 'workflow',
      trigger: { type: 'context', value: '' },
    }
    if (execution === 'workflow') {
      const steps = validateSkillSteps(wizard.skillSteps, wizard.allowedToolIds)
      if (!steps.ok) throw new Error(steps.errors[0] || 'Skill 步骤无效')
      base.skill.chain = steps.chain
    }
    base.interfaces = { method: execution, auth_type: 'none' }
  } else {
    const interfaces = {
      endpoint: wizard.endpoint,
      method: wizard.method || 'POST',
      auth_type: wizard.credentialRef ? 'bearer' : 'none',
    }
    if (wizard.credentialRef) interfaces.auth = { credential_ref: wizard.credentialRef }
    base.interfaces = interfaces
  }
  return base
}

export { pretty as prettyManifest }

export function mcpProbeBody(wizard) {
  if (wizard.mcpTransport === 'stdio') {
    return {
      command_alias: wizard.commandAlias,
      transport: 'stdio',
      method: 'initialize',
    }
  }
  return {
    endpoint: wizard.endpoint,
    token: wizard.token || '',
    method: 'initialize',
    transport: 'streamable_http',
    egress_allowlist: splitAllowlist(wizard.allowlist),
  }
}
