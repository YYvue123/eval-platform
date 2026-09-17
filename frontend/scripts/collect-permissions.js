#!/usr/bin/env node
/**
 * 自动收集前端使用的权限码
 * 扫描 .vue、.js 中的 v-permission、hasPermission、meta.permission
 * 输出到 backend/app/config/permissions.discovered.json
 * 运行: node scripts/collect-permissions.js 或 npm run collect-permissions
 */
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const outputPath = path.resolve(root, '../backend/app/permissions.discovered.json')

const patterns = [
  /v-permission=["']([^"']+)["']/g,
  /v-permission=\[([^\]]+)\]/g,
  /hasPermission\(['"]([^'"]+)['"]\)/g,
  /hasPermission\(`([^`]+)`\)/g,
  /meta\.permission\s*:\s*['"]([^'"]+)['"]/g,
  /permission:\s*['"]([^'"]+)['"]/g,
]

const codes = new Set()

function scanFile(content, filePath) {
  for (const re of patterns) {
    let m
    const regex = new RegExp(re.source, re.flags)
    while ((m = regex.exec(content)) !== null) {
      const raw = m[1]
      if (raw.includes(',')) {
        raw.split(',').forEach((s) => {
          const c = s.replace(/['"\s]/g, '')
          if (c && /^[\w]+:[\w_]+$/.test(c)) codes.add(c)
        })
      } else {
        const c = raw.replace(/['"\s]/g, '')
        if (c && /^[\w]+:[\w_]+$/.test(c)) codes.add(c)
      }
    }
  }
}

function walk(dir) {
  if (!fs.existsSync(dir)) return
  const entries = fs.readdirSync(dir, { withFileTypes: true })
  for (const e of entries) {
    const full = path.join(dir, e.name)
    if (e.isDirectory()) {
      if (e.name !== 'node_modules' && e.name !== 'dist') walk(full)
    } else if (/\.(vue|js|ts|tsx|jsx)$/.test(e.name)) {
      try {
        const content = fs.readFileSync(full, 'utf-8')
        scanFile(content, full)
      } catch (_) {}
    }
  }
}

walk(path.join(root, 'src'))
const list = Array.from(codes).sort()
fs.mkdirSync(path.dirname(outputPath), { recursive: true })
fs.writeFileSync(outputPath, JSON.stringify(list, null, 2), 'utf-8')
console.log(`[collect-permissions] 发现 ${list.length} 个权限码，已写入 permissions.discovered.json`)
