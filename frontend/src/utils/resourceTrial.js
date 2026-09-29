export function formatLatencyMs(value) {
  if (value == null || value === '') return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return String(n)
}

export function pickHistoryLatency(items, correlationId) {
  const list = Array.isArray(items) ? items : []
  if (!correlationId || !list.length) return null
  const row = list.find((item) => item?.correlation_id === correlationId)
  if (!row || row.latency_ms == null || row.latency_ms === '') return null
  const n = Number(row.latency_ms)
  return Number.isFinite(n) ? n : null
}

export function callStatusPhase(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'blocked' || s === 'denied') return 'blocked'
  if (s === 'success' || s === 'completed' || s === 'ok') return 'completed'
  if (s === 'running' || s === 'pending') return 'running'
  return 'failed'
}

export function trialBadgePhase(result) {
  if (result?.ok) return 'completed'
  const s = String(result?.status || '').toLowerCase()
  if (s === 'blocked' || s === 'denied') return 'blocked'
  return 'failed'
}

export function firstValidationMessage(validation) {
  const first = Object.entries(validation?.errors || {})[0]
  return first ? `${first[0]}：${first[1]}` : '请检查输入'
}

export function buildTrialResult(res, browserElapsedMs) {
  const status = String(res?.body?.status || '').toLowerCase()
  const error = res?.body?.error || null
  const ok = status === 'success' && !error
  return {
    ok,
    status,
    statusText: ok ? '执行成功' : `执行失败${error?.code ? ` (${error.code})` : ''}`,
    latency_ms: null,
    browser_latency_ms: Math.round(browserElapsedMs),
    error_code: error?.code || '',
    summary: ok ? res?.body?.result : error,
    raw: res,
  }
}
