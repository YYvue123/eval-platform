import { defineConfig, devices } from '@playwright/test'

/**
 * 浏览器验收：前端默认 http://127.0.0.1:5173，API 经 Vite 代理到隔离后端 :8000。
 * 启动前请用隔离 DATABASE_URL（见 docs/delivery/frontend-ux/UX-SMOKE.md）。
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ['list'],
    ['json', { outputFile: '../docs/delivery/frontend-ux/ux-smoke-playwright.json' }],
  ],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    locale: 'zh-CN',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
