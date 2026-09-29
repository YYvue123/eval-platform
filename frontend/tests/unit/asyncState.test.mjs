import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { ASYNC_STATE_COPY, deriveAsyncState } from '../../src/utils/asyncState.js'

const root = join(dirname(fileURLToPath(import.meta.url)), '../..')

test('deriveAsyncState covers all six branches', () => {
  assert.equal(
    deriveAsyncState({ loading: true, error: null, forbidden: false, items: [], createdOnce: false }),
    'loading',
  )
  assert.equal(
    deriveAsyncState({ loading: false, error: 'boom', forbidden: false, items: [], createdOnce: true }),
    'error',
  )
  assert.equal(
    deriveAsyncState({ loading: false, error: null, forbidden: true, items: [{ id: 1 }], createdOnce: true }),
    'forbidden',
  )
  assert.equal(
    deriveAsyncState({ loading: false, error: null, forbidden: false, items: [], createdOnce: true }),
    'empty',
  )
  assert.equal(
    deriveAsyncState({ loading: false, error: null, forbidden: false, items: [], createdOnce: false }),
    'uncreated',
  )
  assert.equal(
    deriveAsyncState({ loading: false, error: null, forbidden: false, items: [{ id: 1 }], createdOnce: true }),
    'success',
  )
})

test('forbidden wins over loading', () => {
  assert.equal(
    deriveAsyncState({ loading: true, error: 'boom', forbidden: true, items: [], createdOnce: false }),
    'forbidden',
  )
})

test('createdOnce empty vs uncreated', () => {
  const base = { loading: false, error: null, forbidden: false, items: [] }
  assert.equal(deriveAsyncState({ ...base, createdOnce: true }), 'empty')
  assert.equal(deriveAsyncState({ ...base, createdOnce: false }), 'uncreated')
  assert.equal(deriveAsyncState({ ...base, createdOnce: undefined }), 'uncreated')
})

test('ASYNC_STATE_COPY has title and next for every state, no Mock slogans', () => {
  const states = ['loading', 'error', 'forbidden', 'empty', 'uncreated', 'success']
  for (const state of states) {
    assert.equal(typeof ASYNC_STATE_COPY[state].title, 'string')
    assert.ok(ASYNC_STATE_COPY[state].title.length > 0)
    assert.equal(typeof ASYNC_STATE_COPY[state].next, 'string')
    assert.equal(/mock/i.test(JSON.stringify(ASYNC_STATE_COPY[state])), false)
  }
})

test('PageAsyncState shows badge plus copy, slot on success', () => {
  const vue = readFileSync(join(root, 'src/components/PageAsyncState.vue'), 'utf8')
  assert.match(vue, /state/)
  assert.match(vue, /errorMessage/)
  assert.match(vue, /StatusBadge/)
  assert.match(vue, /ASYNC_STATE_COPY/)
  assert.match(vue, /<slot/)
  assert.doesNotMatch(vue, /[Mm]ock/)
  assert.match(vue, /loading:\s*['"]running['"]/)
  assert.match(vue, /error:\s*['"]failed['"]/)
  assert.match(vue, /forbidden:\s*['"]blocked['"]/)
  assert.match(vue, /empty:\s*['"]idle['"]/)
  assert.match(vue, /uncreated:\s*['"]idle['"]/)
})
