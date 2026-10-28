import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { randomId } from '../../src/utils/randomId.js'

const root = join(dirname(fileURLToPath(import.meta.url)), '../..')
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

test('randomId still returns a UUID when randomUUID is unavailable', () => {
  const original = globalThis.crypto.randomUUID
  globalThis.crypto.randomUUID = undefined
  try {
    assert.match(randomId(), uuid)
  } finally {
    globalThis.crypto.randomUUID = original
  }
})

test('randomId falls back when randomUUID throws', () => {
  const original = globalThis.crypto.randomUUID
  globalThis.crypto.randomUUID = () => { throw new Error('insecure') }
  try {
    assert.match(randomId(), uuid)
  } finally {
    globalThis.crypto.randomUUID = original
  }
})

test('eval service dialogs do not call crypto.randomUUID', () => {
  const src = readFileSync(join(root, 'src/views/EvalServices.vue'), 'utf8')
  assert.doesNotMatch(src, /crypto\.randomUUID/)
  assert.match(src, /randomId\(/)
})
