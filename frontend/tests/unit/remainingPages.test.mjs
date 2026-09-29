import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '../..')
function read(rel) {
  return readFileSync(join(root, rel), 'utf8')
}

test('TaskDetail results call includes page, not only page_size: 100 dump', () => {
  const src = read('src/views/TaskDetail.vue')
  assert.doesNotMatch(src, /tasksApi\.results\([^)]*\{\s*page_size:\s*100\s*\}/)
  assert.match(src, /tasksApi\.results\(/)
  assert.match(src, /\bpage\b/)
  assert.match(src, /page_size/)
  assert.match(src, /\btotal\b/)
  assert.match(src, /loadError/)
  assert.match(src, /PageAsyncState/)
  assert.match(src, /catch[\s\S]*loadError/)
})

test('DatasetDetail has loadError and always-visible sample pager', () => {
  const src = read('src/views/DatasetDetail.vue')
  assert.match(src, /loadError/)
  assert.match(src, /catch[\s\S]*loadError/)
  assert.doesNotMatch(src, /itemTotal\s*>\s*itemPageSize/)
  assert.match(src, /el-pagination|第 \{\{/)
  assert.match(src, /PageAsyncState/)
})

test('Leaderboard uses page-header or PageAsyncState', () => {
  const src = read('src/views/Leaderboard.vue')
  assert.match(src, /page-header|PageAsyncState/)
  assert.match(src, /PageAsyncState/)
  assert.match(src, /loadError/)
})

test('AuditLog has disabled export hint, not incomplete-API slogan', () => {
  const src = read('src/views/AuditLog.vue')
  assert.match(src, /当前环境未开放导出/)
  assert.doesNotMatch(src, /API 未完整开放/)
  assert.doesNotMatch(src, /API 尚未完整开放/)
})

test('Users.vue can disable via status update', () => {
  const src = read('src/views/Users.vue')
  assert.match(src, /status:\s*['"]disabled['"]/)
  assert.match(src, /user:edit/)
  assert.match(src, /creatorOptionsError|creatorsLoadError|optionsError/)
})

test('Login.vue catch sets form error, not empty body', () => {
  const src = read('src/views/Login.vue')
  const catchBody = src.match(/catch\s*\([^)]*\)\s*\{([\s\S]*?)\n\s*\}(?:\s*finally)?/)
  assert.ok(catchBody, 'login handleSubmit has catch')
  const body = catchBody[1]
  assert.ok(body.trim().length > 0, 'catch is not empty')
  assert.match(src, /displayMsg|formError|loginError/)
  assert.doesNotMatch(src, /catch\s*\([^)]*\)\s*\{\s*if\s*\(e\?\.errors\)\s*return\s*\}/)
})

test('remaining list-like views use PageAsyncState and loadError', () => {
  const views = [
    'src/views/TaskTemplates.vue',
    'src/views/Benchmarks.vue',
    'src/views/Safety.vue',
    'src/views/Ops.vue',
    'src/views/RolePermission.vue',
    'src/views/NotificationManage.vue',
    'src/views/ApiDocs.vue',
    'src/views/Profile.vue',
  ]
  for (const rel of views) {
    const src = read(rel)
    assert.match(src, /PageAsyncState/, `${rel} PageAsyncState`)
    assert.match(src, /loadError/, `${rel} loadError`)
  }
})
