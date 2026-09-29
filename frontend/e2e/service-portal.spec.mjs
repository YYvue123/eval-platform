import { test, expect } from '@playwright/test'

// UI-only fixtures. These checks are not a real-model or production billing acceptance.
const permissions = ['service:list', 'service:view', 'service:create', 'service:run', 'service:workspace', 'service:credential', 'service:publish', 'user:view']
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('eval_token', 'ui-fixture')
    sessionStorage.setItem('eval_username', 'enterprise-user')
    sessionStorage.setItem('eval_role', 'customer')
  })
  await page.route('**/api/**', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname
    if (!path.startsWith('/api/')) return route.continue()
    let body = { items: [] }
    if (path === '/api/users/me') body = { id: 10, username: 'enterprise-user', role_code: 'customer', permissions, data_scope: 'shared' }
    if (path === '/api/service-portal/workspaces') body = { items: [{ id: 1, name: '远川科技 · 企业空间' }] }
    if (path === '/api/service-portal/assets') body = { datasets: [{ id: 5, name: '客服问答评测集' }], models: [{ id: 2, name: '企业知识助手' }], versions: [{ id: 3, model_id: 2, version: 'V1.0' }] }
    if (path === '/api/service-portal/members') body = { items: [{ id: 10, username: 'enterprise-user', status: 'active' }] }
    if (path === '/api/service-portal/clients') body = { items: [{ id: 8, name: '企业应用', key_prefix: 'evs_fixture', active: true, daily_tokens: 100000, monthly_tokens: 1000000, requests_per_minute: 30, price_fen_per_1k: 2, usage: { daily_used: 5000, monthly_used: 12000, measured_tokens: 8000, amount_fen: 16 } }] }
    if (path === '/api/service-portal/routes') body = { items: [{ id: 4, name: '企业知识助手', stable_id: 1, candidate_id: 2, gray_percent: 10, versions: [{ id: 1, version: 'v1', model_id: 2, model_version_id: 3 }, { id: 2, version: 'v2', model_id: 2, model_version_id: 3 }] }] }
    if (path === '/api/service-portal/evaluations' && req.method() === 'GET') body = { items: [{ id: 1, title: '客服助手能力评测', mode: 'auto', status: 'running', progress: 42, tokens: 1800, reserved_tokens: 5000, amount_fen: 4, billing_status: 'pending', report_ready: false }] }
    if (path === '/api/service-portal/evaluations' && req.method() === 'POST') body = { id: 2, status: 'queued' }
    await route.fulfill({ json: body })
  })
})

test('external customer can refresh portal, configure evaluation and inspect services', async ({ page }) => {
  const errors = []
  page.on('pageerror', err => errors.push(err.message))
  await page.goto('/services')
  await expect(page.getByRole('heading', { name: '评测服务', exact: true })).toBeVisible()
  await expect(page.getByText('客服助手能力评测')).toBeVisible()
  await expect(page.getByText('内部评测委托')).toHaveCount(0)
  await page.getByRole('button', { name: '提交评测需求', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox').first().fill('客户自助评测')
  await page.getByText('专家模式', { exact: true }).click()
  await expect(dialog.getByText('裁判工具', { exact: true })).toBeVisible()
  const submitted = page.waitForRequest(r => r.url().endsWith('/service-portal/evaluations') && r.method() === 'POST')
  await dialog.getByRole('button', { name: '提交需求', exact: true }).click()
  const req = await submitted
  expect(req.postDataJSON().mode).toBe('expert')
  expect(req.headers()['idempotency-key']).toBeTruthy()
  await expect(dialog).not.toBeVisible()
  await page.getByRole('tab', { name: '模型服务与版本' }).click()
  await expect(page.getByText('灰度版本 · 10%')).toBeVisible()
  await page.getByRole('tab', { name: '接入方与用量账单' }).click()
  await expect(page.getByRole('button', { name: '创建接入方' })).toBeVisible()
  await page.getByRole('tab', { name: '企业空间与资产' }).click()
  await expect(page.getByRole('button', { name: '开通企业客户' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '添加成员' })).toBeVisible()
  expect(errors).toEqual([])
})

test('customer portal layout at desktop and mobile sizes', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/services')
  await expect(page.getByText('客服助手能力评测')).toBeVisible()
  await page.screenshot({ path: '../backend/tests/_isolated/service-portal-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: '../backend/tests/_isolated/service-portal-mobile.png', fullPage: true })
  await expect(page.getByRole('button', { name: '提交评测需求', exact: true })).toBeVisible()
})
