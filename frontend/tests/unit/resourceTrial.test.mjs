import test from 'node:test'
import assert from 'node:assert/strict'
import {
  buildTrialResult,
  callStatusPhase,
  firstValidationMessage,
  formatLatencyMs,
  pickHistoryLatency,
  trialBadgePhase,
} from '../../src/utils/resourceTrial.js'

test('trial success requires status success and no error', () => {
  const ok = buildTrialResult(
    { body: { status: 'success', result: { n: 1 } } },
    12.4,
  )
  assert.equal(ok.ok, true)
  assert.equal(ok.statusText, '执行成功')
  assert.equal(ok.latency_ms, null)
  assert.equal(ok.browser_latency_ms, 12)
  assert.deepEqual(ok.summary, { n: 1 })

  const denied = buildTrialResult(
    { body: { status: 'denied', error: { code: 'POLICY' } } },
    8,
  )
  assert.equal(denied.ok, false)
  assert.equal(denied.statusText, '执行失败 (POLICY)')
  assert.equal(denied.error_code, 'POLICY')
  assert.deepEqual(denied.summary, { code: 'POLICY' })
})

test('unknown latency is em dash, never zero', () => {
  assert.equal(formatLatencyMs(null), '—')
  assert.equal(formatLatencyMs(undefined), '—')
  assert.equal(formatLatencyMs(''), '—')
  assert.equal(formatLatencyMs('n/a'), '—')
  assert.equal(formatLatencyMs(42), '42')
  assert.notEqual(formatLatencyMs(null), '0')
})

test('history latency prefers matching item, otherwise absent', () => {
  const items = [
    { correlation_id: 'a', latency_ms: 11 },
    { correlation_id: 'trial-1', latency_ms: 77 },
  ]
  assert.equal(pickHistoryLatency(items, 'trial-1'), 77)
  assert.equal(pickHistoryLatency(items, 'missing'), null)
  assert.equal(pickHistoryLatency(items, null), null)
  assert.equal(pickHistoryLatency([{ latency_ms: null }], 'x'), null)
  assert.equal(pickHistoryLatency([], 'x'), null)
})

test('blocked and denied map to blocked, not completed', () => {
  assert.equal(callStatusPhase('blocked'), 'blocked')
  assert.equal(callStatusPhase('denied'), 'blocked')
  assert.equal(callStatusPhase('success'), 'completed')
  assert.notEqual(callStatusPhase('denied'), 'completed')
})

test('validation message uses first errors entry', () => {
  assert.equal(
    firstValidationMessage({ ok: false, missing: ['a'], errors: { age: '必须是整数', a: '必填' } }),
    'age：必须是整数',
  )
  assert.equal(firstValidationMessage({ ok: false, missing: [], errors: {} }), '请检查输入')
})

test('trial badge uses blocked for denied even if status is not success', () => {
  assert.equal(trialBadgePhase({ ok: true, status: 'success' }), 'completed')
  assert.equal(trialBadgePhase({ ok: false, status: 'denied' }), 'blocked')
  assert.equal(trialBadgePhase({ ok: false, status: 'success' }), 'failed')
})

