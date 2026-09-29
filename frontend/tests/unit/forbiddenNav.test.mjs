import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '../..')

function read(rel) {
  return readFileSync(join(root, rel), 'utf8')
}

test('router sends unauthorized visits to /not-found with reason forbidden', () => {
  const src = read('src/router/index.js')
  assert.match(src, /path:\s*['"]\/not-found['"]/)
  assert.match(src, /reason:\s*['"]forbidden['"]/)
  assert.match(src, /from:\s*to\.fullPath/)
  assert.doesNotMatch(src, /query:\s*\{\s*denied:/)
})

test('Agents does not auto-select first planner model and uses new slogans', () => {
  const src = read('src/views/Agents.vue')
  assert.doesNotMatch(src, /plannerModels\.value\[0\]/)
  assert.match(src, /描述目标、核对计划、批准后执行；执行状态以服务端为准。/)
  assert.doesNotMatch(src, /无 Mock/)
  assert.doesNotMatch(src, /非 Mock/)
  assert.match(src, /开启后按小规模真实样本执行，用量计入同一预算。/)
  assert.match(src, /placeholder="必选"/)
  assert.match(src, /:disabled="!goalText\.trim\(\)\s*\|\|\s*!plannerModelId"[\s\S]*生成计划/)
})

test('Models hint forbids Mock fallback wording', () => {
  const src = read('src/views/Models.vue')
  assert.match(src, /未配置 api_url 时无法探测或试调用。/)
  assert.doesNotMatch(src, /不会回退到本地 Mock/)
  assert.doesNotMatch(src, /留空则使用本地 Mock/)
})

test('NotFound treats reason=forbidden as 403 and sanitizes from as text', () => {
  const src = read('src/views/NotFound.vue')
  assert.match(src, /reason === ['"]forbidden['"]/)
  assert.match(src, /query\.denied/)
  assert.match(src, /无权/)
  assert.match(src, /联系管理员/)
  assert.match(src, /\{\{\s*fromPath\s*\}\}/)
  assert.doesNotMatch(src, /v-html/)
})

test('verify-ux-static requires probe hint and does not treat Mock-fallback slogan as pass', () => {
  const src = read('scripts/verify-ux-static.mjs')
  assert.match(src, /无法探测或试调用/)
  assert.match(src, /留空则使用本地 Mock/)
  assert.doesNotMatch(
    src,
    /if\s*\(!\/不会回退到本地 Mock\/\.test\(models\)/,
  )
  assert.doesNotMatch(src, /!\/不会回退到本地 Mock\/\.test/)
})
