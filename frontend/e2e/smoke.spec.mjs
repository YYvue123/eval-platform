import { test, expect } from '@playwright/test'
import { loginAsAdmin } from './helpers/auth.mjs'

test.describe('smoke · 登录与工作台', () => {
  test('UX-login: 登录后离开 /login 并进入可访问页', async ({ page }) => {
    await loginAsAdmin(page)
    await expect(page).not.toHaveURL(/\/login/)
    await expect(page.locator('.el-menu, .page-title, h2').first()).toBeVisible()
  })

  test('UX-dashboard: 工作台可加载（有权限时）', async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/dashboard')
    if (page.url().includes('/dashboard') && !page.url().includes('denied=')) {
      await expect(page.getByRole('heading', { name: '工作台' })).toBeVisible()
    } else {
      await expect(page).not.toHaveURL(/\/login/)
    }
  })

  test('UX-tasks: 任务列表可达', async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/tasks')
    await expect(page.getByRole('heading', { name: '评测任务' })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('button', { name: '创建任务' }).first()).toBeVisible()
  })

  test('UX-models: 注册表单不再提示本地 Mock', async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/models')
    const createBtn = page.getByRole('button', { name: '注册模型' })
    if (await createBtn.isVisible().catch(() => false)) {
      await createBtn.click()
      await expect(page.getByText('本地 Mock')).toHaveCount(0)
      await expect(page.getByPlaceholder(/真实推理|必填|api_url|URL/i).first()).toBeVisible()
    }
  })
})
