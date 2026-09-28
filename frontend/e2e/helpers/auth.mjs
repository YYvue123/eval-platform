/**
 * @param {import('@playwright/test').Page} page
 * @param {{ username?: string, password?: string }} [creds]
 */
export async function loginAsAdmin(page, creds = {}) {
  const username = creds.username || process.env.E2E_USER || 'admin'
  const password = creds.password || process.env.E2E_PASS || 'admin123'
  await page.goto('/login')
  await page.getByPlaceholder('用户名').fill(username)
  await page.getByPlaceholder('密码').fill(password)
  await page.getByRole('button', { name: '登 录' }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 20_000 })
}
