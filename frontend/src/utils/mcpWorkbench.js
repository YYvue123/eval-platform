export const MCP_RECOVERY = {
  MCP_AUTH_FAILED: '检查凭证引用是否存在且当前服务可读取。',
  MCP_TIMEOUT: '确认服务已启动、地址可访问，并检查超时设置。',
  MCP_SESSION_EXPIRED: '会话已过期，请重新验证连接。',
  MCP_TOOL_ERROR: '连接正常，但工具拒绝了输入；请按 inputSchema 修正参数。',
  MCP_STDIO_NOT_ALLOWED: '该 stdio 别名未获服务端允许。',
  MCP_TRANSPORT_ERROR: '连接中断，请检查传输方式与服务日志。',
  MCP_PROTOCOL_ERROR: '服务返回协议错误，请核对 MCP 版本与方法。',
}

export function emptyMcpState() {
  return {
    phase: 'unconfigured',
    schemaValid: false,
    negotiated: false,
    listed: false,
    lastCall: 'not_run',
    stale: false,
    protocolVersion: '',
    serverName: '',
    toolCount: 0,
    error: null,
  }
}

export function sourceKey(mode, form = {}) {
  const m = String(mode || '')
  if (m === 'registered') return `registered|${String(form.resource_id || '').trim()}`
  return `${m}|${String(form.endpoint || '').trim()}|${String(form.command_alias || '').trim()}`
}

export function probeSourceComplete(mode, form = {}) {
  if (mode === 'registered') return Boolean(String(form.resource_id || '').trim())
  return Boolean(String(form.endpoint || form.command_alias || '').trim())
}

export function probeSchemaValid(mode, form = {}) {
  if (mode === 'registered') return Boolean(String(form.resource_id || '').trim())
  const endpoint = String(form.endpoint || '').trim()
  if (endpoint) return /^https?:\/\//i.test(endpoint)
  return Boolean(String(form.command_alias || '').trim())
}

function currentPhase(state) {
  if (state.lastCall === 'success') return 'success'
  if (state.lastCall === 'failed') return 'failed'
  if (state.listed) return 'listed'
  if (state.negotiated) return 'negotiated'
  if (probeishConfigured(state)) return 'configured'
  return 'unconfigured'
}

function probeishConfigured(state) {
  return Boolean(state.schemaValid) || state.phase === 'configured'
}

export function syncSourceState(prev, { mode, form, catalogStale, sourceChanged } = {}) {
  const key = sourceKey(mode, form)
  const identityChanged = Boolean(sourceChanged) || (prev?.sourceKey != null && prev.sourceKey !== key)
  const complete = probeSourceComplete(mode, form)
  const schemaValid = probeSchemaValid(mode, form)
  const stale = identityChanged ? Boolean(catalogStale) : Boolean(prev?.stale || catalogStale)
  if (identityChanged || !complete) {
    const next = { ...emptyMcpState(), schemaValid, stale, sourceKey: key }
    if (complete) next.phase = 'configured'
    return next
  }
  const next = {
    ...(prev || emptyMcpState()),
    schemaValid,
    stale,
    sourceKey: key,
  }
  if (!next.negotiated && !next.listed && next.lastCall === 'not_run') {
    next.phase = 'configured'
  } else {
    next.phase = currentPhase(next)
  }
  return next
}

export function extractMcpTools(result) {
  if (!result) return []
  if (Array.isArray(result.tools)) return result.tools
  if (Array.isArray(result.result?.tools)) return result.result.tools
  return []
}

export function filterMcpTools(tools, term) {
  const list = Array.isArray(tools) ? tools : []
  const q = String(term || '').trim().toLowerCase()
  if (!q) return list
  return list.filter((tool) =>
    `${tool.name || ''} ${tool.description || ''}`.toLowerCase().includes(q),
  )
}

export function detectCatalogStale(notifications, catalog) {
  if (catalog?.stale) return true
  const list = Array.isArray(notifications) ? notifications : []
  return list.some((note) => {
    const method = typeof note === 'string' ? note : note?.method
    return method === 'notifications/tools/list_changed' || method === 'tools/list_changed'
  })
}

function payloadError(res, caught) {
  if (res?.error && (res.error.code || res.error.message)) {
    return { code: String(res.error.code || 'MCP_PROTOCOL_ERROR'), message: String(res.error.message || '探测失败') }
  }
  if (caught) {
    const data = caught.response?.data
    const nested = data?.error
    if (nested?.code || nested?.message) {
      return { code: String(nested.code || 'MCP_TRANSPORT_ERROR'), message: String(nested.message || data.message || '请求失败') }
    }
    const msg = data?.message ?? data?.detail ?? caught.message
    const text = Array.isArray(msg) ? msg.map((m) => m?.msg || String(m)).join('; ') : String(msg || '请求失败')
    return { code: String(data?.code || 'MCP_TRANSPORT_ERROR'), message: text }
  }
  if (res && res.ok === false) {
    return { code: 'MCP_PROTOCOL_ERROR', message: '探测失败' }
  }
  return null
}

export function formatProbeError(errorObj, caught) {
  const raw = payloadError(errorObj?.code || errorObj?.message ? { error: errorObj } : null, caught) || payloadError({ error: errorObj }, caught)
  const code = raw?.code || 'MCP_TRANSPORT_ERROR'
  const message = raw?.message || '探测失败'
  return {
    code,
    message,
    recovery: MCP_RECOVERY[code] || '请核对连接配置与服务日志后重试。',
  }
}

function serverName(session) {
  const info = session?.server_info
  if (!info || typeof info !== 'object') return ''
  return String(info.name || info.title || '')
}

export function applyProbeResult(prev, method, res, caught) {
  const base = { ...(prev || emptyMcpState()) }
  const ok = Boolean(res && res.ok === true && !caught)
  const err = ok ? null : formatProbeError(res?.error || res, caught)
  const notifyStale = detectCatalogStale(res?.notifications, null)
  const stale = Boolean(base.stale || notifyStale)

  if (method === 'initialize') {
    if (!ok) {
      return {
        success: false,
        tools: [],
        state: {
          ...base,
          phase: base.schemaValid ? 'configured' : 'unconfigured',
          negotiated: false,
          listed: false,
          lastCall: 'not_run',
          protocolVersion: '',
          serverName: '',
          toolCount: 0,
          stale,
          error: err,
        },
      }
    }
    return {
      success: true,
      tools: [],
      state: {
        ...base,
        phase: 'negotiated',
        negotiated: true,
        listed: false,
        lastCall: 'not_run',
        protocolVersion: String(res.session?.protocol_version || ''),
        serverName: serverName(res.session),
        toolCount: 0,
        stale,
        error: null,
      },
    }
  }

  if (method === 'tools/list') {
    if (!ok) {
      return {
        success: false,
        tools: [],
        state: {
          ...base,
          listed: false,
          lastCall: 'not_run',
          toolCount: 0,
          phase: base.negotiated ? 'negotiated' : currentPhase({ ...base, listed: false, lastCall: 'not_run' }),
          stale,
          error: err,
        },
      }
    }
    const tools = extractMcpTools(res.result)
    return {
      success: true,
      tools,
      state: {
        ...base,
        phase: 'listed',
        listed: true,
        lastCall: 'not_run',
        toolCount: tools.length,
        stale: false,
        error: null,
      },
    }
  }

  if (method === 'tools/call') {
    if (!ok) {
      return {
        success: false,
        tools: null,
        state: {
          ...base,
          lastCall: 'failed',
          phase: 'failed',
          stale,
          error: err,
        },
      }
    }
    return {
      success: true,
      tools: null,
      state: {
        ...base,
        lastCall: 'success',
        phase: 'success',
        stale,
        error: null,
      },
    }
  }

  return { success: ok, tools: null, state: { ...base, stale, error: err } }
}
