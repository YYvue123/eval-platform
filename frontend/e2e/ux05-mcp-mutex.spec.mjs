import { test, expect } from '@playwright/test'
import { loginAsAdmin } from './helpers/auth.mjs'

test.describe('UX05 · MCP 来源互斥（UI）', () => {
  test('探测来源 registered/remote 单选互斥', async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/resources')
    await expect(page.getByRole('heading', { name: '工具中心' })).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: 'MCP 连接' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('探测来源')).toBeVisible()

    await dialog.locator('.el-radio-button').filter({ hasText: '临时远程地址' }).click()
    await expect(dialog.getByPlaceholder('https://mcp.example.com/rpc')).toBeVisible()
    // registered 资源选择器在 remote 模式下不渲染
    await expect(dialog.locator('.el-form-item').filter({ hasText: /^资源/ })).toHaveCount(0)

    await dialog.locator('.el-radio-button').filter({ hasText: '已注册连接' }).click()
    await expect(dialog.locator('.el-form-item').filter({ hasText: /^资源/ })).toBeVisible()
    await expect(dialog.getByPlaceholder('https://mcp.example.com/rpc')).toHaveCount(0)
  })
})
