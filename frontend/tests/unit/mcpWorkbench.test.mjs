import test from 'node:test'
import assert from 'node:assert/strict'
import {
  MCP_RECOVERY,
  applyProbeResult,
  detectCatalogStale,
  emptyMcpState,
  extractMcpTools,
  filterMcpTools,
  formatProbeError,
  probeSchemaValid,
  probeSourceComplete,
  sourceKey,
  syncSourceState,
} from '../../src/utils/mcpWorkbench.js'

test('incomplete source stays unconfigured and is not schema-valid', () => {
  const next = syncSourceState(emptyMcpState(), {
    mode: 'registered',
    form: { resource_id: '', endpoint: '' },
  })
  assert.equal(next.phase, 'unconfigured')
  assert.equal(next.schemaValid, false)
  assert.equal(probeSourceComplete('remote', { endpoint: '' }), false)
  assert.equal(probeSchemaValid('remote', { endpoint: 'mcp.local' }), false)
})

test('complete http source is configured and schema-valid', () => {
  const next = syncSourceState(emptyMcpState(), {
    mode: 'remote',
    form: { endpoint: 'https://mcp.example.com/rpc' },
  })
  assert.equal(next.phase, 'configured')
  assert.equal(next.schemaValid, true)
  assert.equal(probeSourceComplete('registered', { resource_id: 'mcp.stats' }), true)
})

test('initialize success maps session fields and does not treat ok=false as negotiated', () => {
  const negotiated = applyProbeResult(emptyMcpState(), 'initialize', {
    ok: true,
    session: {
      protocol_version: '2024-11-05',
      server_info: { name: 'stats-local' },
    },
    notifications: [],
  })
  assert.equal(negotiated.state.phase, 'negotiated')
  assert.equal(negotiated.state.negotiated, true)
  assert.equal(negotiated.state.protocolVersion, '2024-11-05')
  assert.equal(negotiated.state.serverName, 'stats-local')
  assert.equal(negotiated.success, true)

  const failed = applyProbeResult(negotiated.state, 'initialize', {
    ok: false,
    error: { code: 'MCP_AUTH_FAILED', message: '401' },
    session: { protocol_version: '2024-11-05', server_info: { name: 'stale-name' } },
  })
  assert.equal(failed.success, false)
  assert.equal(failed.state.negotiated, false)
  assert.equal(failed.state.listed, false)
  assert.equal(failed.state.lastCall, 'not_run')
  assert.equal(failed.state.protocolVersion, '')
  assert.equal(failed.state.serverName, '')
  assert.equal(failed.state.error.code, 'MCP_AUTH_FAILED')
})

test('failed initialize clears later green steps', () => {
  const listed = {
    ...emptyMcpState(),
    phase: 'listed',
    schemaValid: true,
    negotiated: true,
    listed: true,
    lastCall: 'success',
    protocolVersion: '2024-11-05',
    serverName: 'stats',
    toolCount: 3,
  }
  const failed = applyProbeResult(listed, 'initialize', {
    ok: false,
    error: { code: 'MCP_TIMEOUT', message: 'timed out' },
  })
  assert.equal(failed.state.listed, false)
  assert.equal(failed.state.lastCall, 'not_run')
  assert.equal(failed.state.toolCount, 0)
  assert.notEqual(failed.state.phase, 'listed')
})

test('tools/list success sets listed count; stale stays until list succeeds', () => {
  const stale = {
    ...emptyMcpState(),
    phase: 'negotiated',
    negotiated: true,
    stale: true,
  }
  const stillStale = applyProbeResult(stale, 'tools/list', {
    ok: false,
    error: { code: 'MCP_PROTOCOL_ERROR', message: 'bad method' },
    notifications: [{ method: 'notifications/tools/list_changed' }],
  })
  assert.equal(stillStale.state.stale, true)
  assert.equal(stillStale.state.listed, false)

  const listed = applyProbeResult(stale, 'tools/list', {
    ok: true,
    result: { tools: [{ name: 'sum' }, { name: 'mean' }] },
  })
  assert.equal(listed.state.listed, true)
  assert.equal(listed.state.toolCount, 2)
  assert.equal(listed.state.stale, false)
  assert.equal(listed.state.phase, 'listed')
})

test('sourceKey distinguishes resource_id, endpoint, and mode', () => {
  assert.equal(
    sourceKey('registered', { resource_id: 'mcp.stats' }),
    sourceKey('registered', { resource_id: 'mcp.stats' }),
  )
  assert.notEqual(
    sourceKey('registered', { resource_id: 'mcp.stats' }),
    sourceKey('registered', { resource_id: 'mcp.other' }),
  )
  assert.notEqual(
    sourceKey('remote', { endpoint: 'https://a.example/rpc' }),
    sourceKey('remote', { endpoint: 'https://b.example/rpc' }),
  )
  assert.notEqual(
    sourceKey('registered', { resource_id: 'mcp.stats' }),
    sourceKey('remote', { endpoint: 'https://mcp.example.com/rpc', resource_id: 'mcp.stats' }),
  )
})

test('source identity change does not inherit prev.stale', () => {
  const prev = syncSourceState(
    { ...emptyMcpState(), stale: true },
    { mode: 'registered', form: { resource_id: 'mcp.stats' }, catalogStale: true },
  )
  assert.equal(prev.stale, true)
  const next = syncSourceState(prev, {
    mode: 'registered',
    form: { resource_id: 'mcp.other' },
    catalogStale: false,
  })
  assert.equal(next.stale, false)
  const viaFlag = syncSourceState(prev, {
    mode: 'registered',
    form: { resource_id: 'mcp.other' },
    catalogStale: false,
    sourceChanged: true,
  })
  assert.equal(viaFlag.stale, false)
})

test('after identity change stale comes only from catalogStale', () => {
  const prev = syncSourceState(emptyMcpState(), {
    mode: 'registered',
    form: { resource_id: 'mcp.stats' },
    catalogStale: true,
  })
  assert.equal(prev.stale, true)
  const fromNewCatalog = syncSourceState(prev, {
    mode: 'registered',
    form: { resource_id: 'mcp.other' },
    catalogStale: true,
  })
  assert.equal(fromNewCatalog.stale, true)
  const fromNewFresh = syncSourceState(prev, {
    mode: 'remote',
    form: { endpoint: 'https://mcp.example.com/rpc' },
    catalogStale: false,
    sourceChanged: true,
  })
  assert.equal(fromNewFresh.stale, false)
})

test('same source keeps prev.stale or catalogStale until successful tools/list', () => {
  const configured = syncSourceState(emptyMcpState(), {
    mode: 'registered',
    form: { resource_id: 'mcp.stats' },
  })
  const fromCatalog = syncSourceState(configured, {
    mode: 'registered',
    form: { resource_id: 'mcp.stats' },
    catalogStale: true,
  })
  assert.equal(fromCatalog.stale, true)
  const stillStale = syncSourceState(fromCatalog, {
    mode: 'registered',
    form: { resource_id: 'mcp.stats' },
    catalogStale: false,
  })
  assert.equal(stillStale.stale, true)
  const listed = applyProbeResult(stillStale, 'tools/list', {
    ok: true,
    result: { tools: [{ name: 'sum' }] },
  })
  assert.equal(listed.state.stale, false)
})

test('list_changed and catalog.stale mark stale', () => {
  assert.equal(detectCatalogStale([{ method: 'notifications/tools/list_changed' }], null), true)
  assert.equal(detectCatalogStale([], { stale: true }), true)
  assert.equal(detectCatalogStale([], { stale: false }), false)
})

test('tools/call ok=false is lastCall failed, not success', () => {
  const listed = {
    ...emptyMcpState(),
    phase: 'listed',
    negotiated: true,
    listed: true,
    toolCount: 1,
  }
  const failed = applyProbeResult(listed, 'tools/call', {
    ok: false,
    error: { code: 'MCP_TOOL_ERROR', message: 'bad args' },
  })
  assert.equal(failed.success, false)
  assert.equal(failed.state.lastCall, 'failed')
  assert.equal(failed.state.phase, 'failed')
  assert.equal(failed.state.listed, true)

  const ok = applyProbeResult(listed, 'tools/call', { ok: true, result: { content: [] } })
  assert.equal(ok.state.lastCall, 'success')
  assert.equal(ok.state.phase, 'success')
})

test('recovery map covers stable MCP codes and http catch payload', () => {
  assert.match(MCP_RECOVERY.MCP_AUTH_FAILED, /凭证/)
  assert.match(MCP_RECOVERY.MCP_TIMEOUT, /超时/)
  const formatted = formatProbeError({ code: 'MCP_SESSION_EXPIRED', message: 'gone' })
  assert.equal(formatted.code, 'MCP_SESSION_EXPIRED')
  assert.equal(formatted.message, 'gone')
  assert.equal(formatted.recovery, MCP_RECOVERY.MCP_SESSION_EXPIRED)
  const http = formatProbeError(null, { response: { data: { error: { code: 'MCP_STDIO_NOT_ALLOWED', message: 'alias' } } } })
  assert.equal(http.code, 'MCP_STDIO_NOT_ALLOWED')
  assert.notEqual(http.message, 'Error: alias')
})

test('tool search matches name and description', () => {
  const tools = extractMcpTools({ result: { tools: [{ name: 'sum', description: '加法' }, { name: 'mean' }] } })
  assert.equal(tools.length, 2)
  assert.equal(filterMcpTools(tools, 'mean').length, 1)
  assert.equal(filterMcpTools(tools, '加法')[0].name, 'sum')
  assert.equal(filterMcpTools(tools, '  ').length, 2)
})
