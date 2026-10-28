import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '../..')

test('ops probes do not toast when readiness or metrics are unavailable', () => {
  const src = readFileSync(join(root, 'src/api/index.js'), 'utf8')
  assert.match(src, /ready:\s*\(\)\s*=>\s*request\.get\('\/ready',\s*\{\s*skipErrorToast:\s*true\s*\}\)/)
  assert.match(src, /metrics:\s*\(\)\s*=>\s*request\.get\('\/metrics',\s*\{\s*responseType:\s*'text',\s*skipErrorToast:\s*true\s*\}\)/)
})

test('nginx proxies API docs and metrics instead of returning 403', () => {
  const src = readFileSync(join(root, '../deploy/ubuntu/nginx.conf.template'), 'utf8')
  assert.doesNotMatch(src, /location = \/api\/metrics \{ return 403; \}/)
  assert.doesNotMatch(src, /openapi\\.json\)\(\/\|\$\) \{ return 403; \}/)
  assert.match(src, /location ~ \^\/\(docs\|redoc\|openapi\\\.json\)/)
  assert.match(src, /proxy_pass \$backend\$request_uri;/)
})
