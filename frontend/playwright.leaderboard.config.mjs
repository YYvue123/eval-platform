import { defineConfig } from '@playwright/test'
// The API at :8011 MUST use backend/tests/_isolated/leaderboard-ui-v2.db.
export default defineConfig({ testDir: './e2e', testMatch: 'leaderboard-v2.spec.mjs', workers: 1, timeout: 90000,
  reporter: [['list']], outputDir: './test-results/leaderboard', use: { baseURL: 'http://127.0.0.1:5181', viewport: { width: 1440, height: 1050 }, locale: 'zh-CN' } })
