#!/usr/bin/env node
/**
 * L0 UX 静态门禁：路由权限、导航候选、权限采集产物一致性。
 * 不代替浏览器 UX01–16。
 */
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const errors = []
const warnings = []

function read(p) {
  return fs.readFileSync(p, 'utf-8')
}

// 1) router 中带 permission 的 path 与 navigation CANDIDATES 对齐（业务页）
const routerSrc = read(path.join(root, 'src/router/index.js'))
const navSrc = read(path.join(root, 'src/utils/navigation.js'))
const routePerms = [...routerSrc.matchAll(/path:\s*'([^']+)'[^\n]*permission:\s*'([^']+)'/g)]
  .map((m) => ({ path: m[1].startsWith('/') ? m[1] : `/${m[1]}`, permission: m[2] }))
  .filter((r) => !r.path.includes(':pathMatch') && r.path !== '/login')

const candPaths = [...navSrc.matchAll(/path:\s*'([^']+)'/g)].map((m) => m[1])
const requiredNav = [
  '/dashboard', '/agents', '/tasks', '/datasets', '/models',
  '/resources', '/services', '/leaderboard', '/ops', '/users',
  '/notifications', '/audit', '/profile',
]
for (const p of requiredNav) {
  if (!candPaths.includes(p)) errors.push(`navigation.js 缺少候选 ${p}`)
}

// 2) Login / NotFound / router 引用 safeHomePath | firstAccessiblePath
for (const rel of ['src/views/Login.vue', 'src/views/NotFound.vue', 'src/router/index.js']) {
  const s = read(path.join(root, rel))
  if (!/safeHomePath|firstAccessiblePath/.test(s)) {
    errors.push(`${rel} 未引用安全回跳 helper`)
  }
}

// 3) 无 Mock 文案回归（Models 接入提示）
const models = read(path.join(root, 'src/views/Models.vue'))
if (/留空则使用本地 Mock/.test(models)) {
  errors.push('Models.vue 仍提示本地 Mock')
}
if (!/不会回退到本地 Mock/.test(models) && !/无法正式调用/.test(models)) {
  warnings.push('Models.vue 建议明示无 api_url 不可正式调用')
}

// 4) permissions.discovered.json 存在且非空
const discPath = path.resolve(root, '../backend/app/permissions.discovered.json')
if (!fs.existsSync(discPath)) {
  errors.push('缺少 permissions.discovered.json（先 npm run collect-permissions）')
} else {
  const list = JSON.parse(read(discPath))
  if (!Array.isArray(list) || list.length < 20) {
    errors.push(`permissions.discovered.json 异常：length=${list?.length}`)
  }
  const must = ['dashboard:view', 'task:list', 'agent:list', 'resource:list', 'service:list']
  for (const c of must) {
    if (!list.includes(c)) errors.push(`discovered 缺少权限 ${c}`)
  }
}

// 5) 关键页存在 StatusBadge / ResourcePicker 引用（抽样）
const tasks = read(path.join(root, 'src/views/Tasks.vue'))
if (!tasks.includes('ResourcePicker') || !tasks.includes('StatusBadge')) {
  errors.push('Tasks.vue 缺少 ResourcePicker 或 StatusBadge')
}
const safety = read(path.join(root, 'src/views/Safety.vue'))
if (!safety.includes('expert_label') || !safety.includes('needs_evidence')) {
  errors.push('Safety.vue 缺少完整复核标签')
}
const services = read(path.join(root, 'src/views/EvalServices.vue'))
if (!services.includes('primaryActions') || !services.includes('moreActions')) {
  errors.push('EvalServices.vue 未收敛办理动作')
}

// 6) 路由 permission 抽样：safety/services
const needRoutes = [
  { path: 'safety', perm: 'task:list' },
  { path: 'services', perm: 'service:list' },
  { path: 'agents', perm: 'agent:list' },
]
for (const nr of needRoutes) {
  const hit = routePerms.find((r) => r.path === `/${nr.path}` || r.path === nr.path)
  if (!hit) warnings.push(`未能解析路由 ${nr.path} 的 permission（检查 router 格式）`)
  else if (hit.permission !== nr.perm) errors.push(`路由 ${nr.path} permission=${hit.permission} 期望 ${nr.perm}`)
}

const report = {
  ok: errors.length === 0,
  errors,
  warnings,
  route_permission_samples: routePerms.slice(0, 12),
  nav_candidates: candPaths,
  checked_at: new Date().toISOString(),
}

const outDir = path.resolve(root, '../docs/delivery/frontend-ux')
fs.mkdirSync(outDir, { recursive: true })
fs.writeFileSync(path.join(outDir, 'u5-static-verify.json'), JSON.stringify(report, null, 2), 'utf-8')

if (warnings.length) {
  console.warn('[verify:ux-static] warnings:')
  warnings.forEach((w) => console.warn(' -', w))
}
if (errors.length) {
  console.error('[verify:ux-static] FAILED')
  errors.forEach((e) => console.error(' -', e))
  process.exit(1)
}
console.log('[verify:ux-static] OK')
console.log(`  routes sampled=${routePerms.length} nav=${candPaths.length} warnings=${warnings.length}`)
