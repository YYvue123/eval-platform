import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '../..')
function read(rel) {
  return readFileSync(join(root, rel), 'utf8')
}

const LIST_VIEWS = [
  'src/views/Datasets.vue',
  'src/views/Tasks.vue',
  'src/views/Quality.vue',
  'src/views/Prompts.vue',
  'src/views/EvalServices.vue',
  'src/views/Users.vue',
  'src/views/AuditLog.vue',
]

test('Datasets.vue and Users.vue do not hide pager with total > pageSize', () => {
  const datasets = read('src/views/Datasets.vue')
  const users = read('src/views/Users.vue')
  assert.doesNotMatch(datasets, /v-if="total > pageSize"/)
  assert.doesNotMatch(users, /total > pageSize/)
})

test('Quality/Prompts/EvalServices page with page+page_size and total, not dump 50', () => {
  const quality = read('src/views/Quality.vue')
  const prompts = read('src/views/Prompts.vue')
  const evals = read('src/views/EvalServices.vue')

  assert.doesNotMatch(quality, /qualityApi\.list\(\{\s*page_size:\s*50\s*\}\)/)
  assert.doesNotMatch(quality, /qualityApi\.issues\(\{\s*page_size:\s*50/)
  assert.doesNotMatch(prompts, /promptsApi\.list\(\{\s*page_size:\s*50\s*\}\)/)
  assert.doesNotMatch(evals, /servicesApi\.list\(\{\s*page_size:\s*50\s*\}\)/)

  for (const [name, src] of [
    ['Quality', quality],
    ['Prompts', prompts],
    ['EvalServices', evals],
  ]) {
    assert.match(src, /\bpage\b/, `${name} passes page`)
    assert.match(src, /page_size/, `${name} passes page_size`)
    assert.match(src, /\btotal\b/, `${name} reads total`)
  }
})

test('seven list views sync URL via readListQuery or writeListQuery', () => {
  for (const rel of LIST_VIEWS) {
    const src = read(rel)
    assert.ok(
      /readListQuery|writeListQuery/.test(src),
      `${rel} must call readListQuery or writeListQuery`,
    )
  }
})

test('ResourcePicker pages beyond first 30 via 加载更多 or page increment', () => {
  const src = read('src/components/ResourcePicker.vue')
  assert.match(src, /加载更多|__more__/)
  assert.match(src, /\bpage\b/)
  assert.match(src, /loadError/)
})

test('Users.vue catch sets loadError instead of silent empty items', () => {
  const src = read('src/views/Users.vue')
  assert.match(src, /loadError/)
  assert.match(src, /catch[\s\S]*loadError/)
  assert.doesNotMatch(src, /catch\s*\([^)]*\)\s*\{\s*items\.value\s*=\s*\[\s*\]/)
})
