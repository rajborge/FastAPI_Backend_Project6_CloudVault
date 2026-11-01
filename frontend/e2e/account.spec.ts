import { expect, test } from '@playwright/test'

test('email link verifies its token and offers a return to the workspace', async ({ page }) => {
  let submitted = ''
  await page.route('http://localhost:8000/auth/verify-email', async (route) => {
    submitted = route.request().postDataJSON().token
    await route.fulfill({ status: 204 })
  })
  await page.goto('/?account_action=verify&token=test-verification-token-long-enough')
  await expect(page.getByRole('heading', { name: 'Verify your email' })).toBeVisible()
  await expect(page).not.toHaveURL(/token=/)
  await page.getByRole('button', { name: 'Verify email', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Email verified')
  expect(submitted).toBe('test-verification-token-long-enough')
  await expect(page.getByRole('link', { name: 'Return to CloudVault' })).toBeVisible()
  await page.screenshot({ path: 'test-results/account-verification.png', fullPage: true })
})

test('MFA setup explains authenticator codes and works before email verification', async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('cloudvault.access', 'test-access'))
  await page.route('http://localhost:8000/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/notifications/stream') return route.fulfill({ contentType: 'text/event-stream', body: ': heartbeat\n\n' })
    if (path === '/folders/root') return route.fulfill({ json: { files: [], folders: [] } })
    if (path === '/auth/email-status') return route.fulfill({ json: { email: 'tester@example.com', is_verified: false, delivery_status: 'NOT_REQUESTED' } })
    if (path === '/auth/mfa/setup') return route.fulfill({ json: { secret: 'TESTKEYFORBROWSERONLY' } })
    if (path === '/auth/mfa/enable') {
      expect(route.request().postDataJSON().code).toBe('123456')
      return route.fulfill({ json: { access_token: 'new-test-access', csrf_token: 'test-csrf', token_type: 'Bearer', recovery_codes: ['test-recovery-code'] } })
    }
    return route.fulfill({ json: {} })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Account security' }).click()
  const dialog = page.getByRole('dialog', { name: 'Account security' })
  await dialog.getByLabel('Current password', { exact: true }).fill('TestPassword123')
  await dialog.getByRole('button', { name: 'Set up MFA', exact: true }).click()
  await expect(dialog.getByText('TESTKEYFORBROWSERONLY', { exact: true })).toBeVisible()
  await dialog.getByLabel('6-digit authenticator code', { exact: true }).fill('123456')
  await dialog.getByRole('button', { name: 'Enable MFA', exact: true }).click()
  await expect(dialog.getByText('test-recovery-code', { exact: true })).toBeVisible()
  await page.screenshot({ path: 'test-results/account-security.png', fullPage: true })
})
