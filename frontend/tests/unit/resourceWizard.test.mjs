import test from 'node:test'
import assert from 'node:assert/strict'
import {
  ADVANCED_SCHEMA_HINT,
  DEFAULT_SKILL_INPUTS,
  buildManifest,
  buildMcpInterfaces,
  emptyWizard,
  isHttpUrl,
  isInvocableTool,
  mergeToolPages,
  parseInputJson,
  schemaFormSync,
  skillCheckNotes,
  validateSkillSteps,
  validateWizardConnect,
} from '../../src/utils/resourceWizard.js'

test('emptyWizard includes mcp transport and two skill json steps', () => {
  const w = emptyWizard()
  assert.equal(w.mcpTransport, 'streamable_http')
  assert.equal(w.commandAlias, '')
  assert.equal(w.skillSteps.length, 2)
  assert.equal(w.skillSteps[0].step_id, 's1')
  assert.equal(w.skillSteps[0].resource_id, '')
  assert.equal(w.skillSteps[0].inputJson, DEFAULT_SKILL_INPUTS.s1)
  assert.equal(w.skillSteps[1].inputJson, DEFAULT_SKILL_INPUTS.s2)
  assert.ok(!Object.prototype.hasOwnProperty.call(w.skillSteps[0], 'input_ref'))
})

test('parseInputJson keeps original text on failure and requires object', () => {
  const bad = parseInputJson('{not json', '{not json')
  assert.equal(bad.ok, false)
  assert.equal(bad.kept, '{not json')
  assert.match(bad.error, /JSON/)

  const arr = parseInputJson('[]')
  assert.equal(arr.ok, false)
  assert.equal(arr.kept, '[]')

  const ok = parseInputJson('{"text":{"$ref":"$input.text"}}')
  assert.equal(ok.ok, true)
  assert.deepEqual(ok.value.text, { $ref: '$input.text' })
})

test('validateSkillSteps requires unique ids, selected tools, and object json', () => {
  const allowed = new Set(['builtin/exact_match', 'builtin/parse_stats'])
  const missing = validateSkillSteps([
    { step_id: 's1', resource_id: '', inputJson: '{}' },
  ], allowed)
  assert.equal(missing.ok, false)
  assert.match(missing.errors[0], /s1/)

  const dup = validateSkillSteps([
    { step_id: 's1', resource_id: 'builtin/exact_match', inputJson: '{}' },
    { step_id: 's1', resource_id: 'builtin/parse_stats', inputJson: '{}' },
  ], allowed)
  assert.equal(dup.ok, false)
  assert.match(dup.errors.join(' '), /唯一/)

  const typed = validateSkillSteps([
    { step_id: 's1', resource_id: 'not/in/list', inputJson: '{}' },
  ], allowed)
  assert.equal(typed.ok, false)

  const ok = validateSkillSteps([
    { step_id: 's1', resource_id: 'builtin/exact_match', inputJson: DEFAULT_SKILL_INPUTS.s1 },
    { step_id: 's2', resource_id: 'builtin/parse_stats', inputJson: DEFAULT_SKILL_INPUTS.s2 },
  ], allowed)
  assert.equal(ok.ok, true)
  assert.deepEqual(ok.chain[1].input.values, { $ref: 's1.output.values' })
})

test('skillCheckNotes flags unknown refs without claiming invoke success', () => {
  const notes = skillCheckNotes([
    { step_id: 's1', resource_id: 'builtin/exact_match', inputJson: DEFAULT_SKILL_INPUTS.s1 },
    { step_id: 's2', resource_id: 'builtin/parse_stats', inputJson: '{"x":{"$ref":"s9.output.values"}}' },
  ])
  assert.equal(notes.ok, false)
  assert.match(notes.message, /s2/)
  assert.doesNotMatch(notes.message, /成功/)
})

test('validateWizardConnect covers http tool, streamable http, and stdio alias', () => {
  assert.equal(isHttpUrl('https://tool.example/invoke'), true)
  assert.equal(isHttpUrl('ftp://x'), false)

  const tool = validateWizardConnect({ kind: 'tool', endpoint: 'not-url' })
  assert.equal(tool.ok, false)

  const httpMcp = validateWizardConnect({
    kind: 'mcp',
    mcpTransport: 'streamable_http',
    endpoint: 'https://mcp.example/rpc',
    commandAlias: '',
    stdioAliases: ['stats'],
  })
  assert.equal(httpMcp.ok, true)

  const stdioMissing = validateWizardConnect({
    kind: 'mcp',
    mcpTransport: 'stdio',
    endpoint: 'https://ignored',
    commandAlias: 'stats',
    stdioAliases: [],
  })
  assert.equal(stdioMissing.ok, false)

  const stdioOk = validateWizardConnect({
    kind: 'mcp',
    mcpTransport: 'stdio',
    commandAlias: 'stats',
    stdioAliases: ['stats'],
  })
  assert.equal(stdioOk.ok, true)

  const stdioTyped = validateWizardConnect({
    kind: 'mcp',
    mcpTransport: 'stdio',
    commandAlias: 'evil',
    stdioAliases: ['stats'],
  })
  assert.equal(stdioTyped.ok, false)
})

test('buildMcpInterfaces branches transport and does not mix sources', () => {
  assert.deepEqual(
    buildMcpInterfaces({
      mcpTransport: 'stdio',
      commandAlias: 'stats',
      endpoint: 'https://should-not-appear',
      credentialRef: 'TOKEN',
    }),
    { transport: 'stdio', command_alias: 'stats' },
  )
  const http = buildMcpInterfaces({
    mcpTransport: 'streamable_http',
    endpoint: 'https://mcp.example/rpc',
    credentialRef: 'TOKEN',
    allowlist: 'host1, host2',
  })
  assert.equal(http.transport, 'streamable_http')
  assert.equal(http.endpoint, 'https://mcp.example/rpc')
  assert.equal(http.method, 'POST')
  assert.equal(http.auth_type, 'bearer')
  assert.deepEqual(http.auth, { credential_ref: 'TOKEN' })
  assert.deepEqual(http.egress_allowlist, ['host1', 'host2'])
})

test('schemaFormSync never maps integer to number and keeps advanced json', () => {
  const simple = schemaFormSync('{"type":"object","properties":{"n":{"type":"integer"}},"required":["n"]}', [])
  assert.equal(simple.advancedKept, false)
  assert.equal(simple.fields[0].type, 'integer')

  const advanced = schemaFormSync(
    JSON.stringify({
      type: 'object',
      properties: {
        mode: { type: 'string', enum: ['a', 'b'], description: 'x' },
        nested: { type: 'object', properties: { k: { type: 'string' } } },
        n: { type: 'number', minimum: 1 },
      },
    }),
    [{ key: 'old', type: 'string', required: false }],
  )
  assert.equal(advanced.advancedKept, true)
  assert.equal(advanced.hint, ADVANCED_SCHEMA_HINT)
  assert.deepEqual(advanced.fields, [{ key: 'old', type: 'string', required: false }])
})

test('isInvocableTool includes registered HTTP tools, not only online', () => {
  assert.equal(isInvocableTool({ status: 'registered' }), true)
  assert.equal(isInvocableTool({ status: 'online' }), true)
  assert.equal(isInvocableTool({ status: 'offline' }), false)
})

test('mergeToolPages appends unique resource_id rows for server pagination', () => {
  const first = mergeToolPages([], {
    items: [{ resource_id: 'a', name: 'A', version: '1', health_status: 'online' }],
    page: 1,
    total: 3,
  })
  const second = mergeToolPages(first.items, {
    items: [
      { resource_id: 'a', name: 'A2' },
      { resource_id: 'b', name: 'B', version: '2', health_status: 'online' },
    ],
    page: 2,
    total: 3,
  })
  assert.equal(second.items.length, 2)
  assert.equal(second.items[0].name, 'A2')
  assert.equal(second.hasMore, true)
})

test('buildManifest skill chain uses parsed input objects', () => {
  const w = emptyWizard()
  w.kind = 'skill'
  w.ns = 'demo'
  w.slug = 'dual'
  w.name = 'dual'
  w.skillSteps[0].resource_id = 'builtin/exact_match'
  w.skillSteps[1].resource_id = 'builtin/parse_stats'
  const mf = buildManifest(w)
  assert.equal(mf.skill.chain[0].input.text.$ref, '$input.text')
  assert.equal(mf.skill.chain[1].input.values.$ref, 's1.output.values')
  assert.equal(mf.interfaces.method, 'workflow')
})
