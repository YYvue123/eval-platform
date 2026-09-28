import { test, expect } from '@playwright/test'
import { loginAsAdmin } from './helpers/auth.mjs'

test.describe('Safety / Services 可达', () => {
  test('UX12-nav: 安全可信页可打开复核或试评入口', async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/safety')
    await expect(page.getByRole('heading', { name: '安全可信评测' })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/专家复核|固定集|试评/).first()).toBeVisible()
    const reviewBtn = page.getByRole('button', { name: '复核' }).first()
    if (await reviewBtn.isVisible().catch(() => false)) {
      await reviewBtn.click()
      await expect(page.getByText(/人工标签|候选输出|驳回|需补证/).first()).toBeVisible()
    }
  })

  test('EvalServices: 服务页可打开', async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/services')
    await expect(page.getByRole('heading', { name: '评测服务' })).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('.el-table, .el-empty').first()).toBeVisible()
  })
})
