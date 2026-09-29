import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { readListQuery, writeListQuery } from '../../src/utils/listQuery.js'

const root = join(dirname(fileURLToPath(import.meta.url)), '../..')

test('missing query → page 1, page_size 20, q empty, status empty', () => {
  assert.deepEqual(readListQuery(), { page: 1, page_size: 20, q: '', status: '' })
  assert.deepEqual(readListQuery({}), { page: 1, page_size: 20, q: '', status: '' })
})

test('page=0 or NaN → 1', () => {
  assert.equal(readListQuery({ page: '0' }).page, 1)
  assert.equal(readListQuery({ page: 'nope' }).page, 1)
  assert.equal(readListQuery({ page: undefined }).page, 1)
})

test('page_size=500 → 100', () => {
  assert.equal(readListQuery({ page_size: '500' }).page_size, 100)
})

test('writeListQuery merges and drops empty keys', async () => {
  const calls = []
  const router = {
    currentRoute: { value: { query: { page: '2', keep: 'yes', q: 'old' } } },
    replace: async (loc) => {
      calls.push(loc)
      return loc
    },
  }
  await writeListQuery(router, { q: '', status: 'queued', page: 3 })
  assert.equal(calls.length, 1)
  assert.deepEqual(calls[0].query, { page: '3', keep: 'yes', status: 'queued' })
})

test('request interceptor honors skipErrorToast and still rejects', () => {
  const src = readFileSync(join(root, 'src/utils/request.js'), 'utf8')
  assert.match(src, /error\.config\?\.skipErrorToast/)
  assert.match(src, /error\.response\?\.config\?\.skipErrorToast/)
  assert.match(src, /skipErrorToast/)
  assert.match(src, /ElMessage\.error/)
  assert.match(src, /userStore\.logout\(\)/)
  assert.match(src, /Promise\.reject\(error\)/)
  assert.doesNotMatch(src, /if \(status === 401\)[\s\S]*ElMessage\.error[\s\S]*skipErrorToast/)
})

test('unread-count polling sets skipErrorToast', () => {
  const src = readFileSync(join(root, 'src/api/index.js'), 'utf8')
  assert.match(
    src,
    /getUnreadCount:\s*\(\)\s*=>\s*request\.get\('\/notifications\/mine\/unread-count',\s*\{\s*skipErrorToast:\s*true\s*\}\)/,
  )
})

test('Dashboard load failure sets loadError and uses PageAsyncState', () => {
  const src = readFileSync(join(root, 'src/views/Dashboard.vue'), 'utf8')
  assert.match(src, /loadError/)
  assert.match(src, /PageAsyncState/)
  assert.match(src, /state="error"/)
  assert.match(src, /:errorMessage="loadError"/)
  assert.doesNotMatch(src, /workbench\.value = \{ todos: \[\], running: \[\], failed: \[\], recent: \[\] \}/)
})

test('Agents loadList sets error flags instead of silent empty lists', () => {
  const src = readFileSync(join(root, 'src/views/Agents.vue'), 'utf8')
  assert.match(src, /modelsLoadError/)
  assert.match(src, /sessionsLoadError/)
  assert.doesNotMatch(src, /modelsApi\.list\([^)]*\)\.catch\(\(\) => \(\{ items: \[\] \}\)\)/)
  assert.match(src, /v-if="sessionsLoadError"/)
  assert.match(src, /modelsLoadError/)
})

test('NotificationManage loadUsers sets usersLoadError', () => {
  const src = readFileSync(join(root, 'src/views/NotificationManage.vue'), 'utf8')
  assert.match(src, /usersLoadError/)
  assert.match(src, /v-if="usersLoadError"/)
})
