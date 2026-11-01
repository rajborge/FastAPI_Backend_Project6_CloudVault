import { createServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import { expect, test, type Page } from '@playwright/test'

const file = { id: 'a0', original_name: 'notes.txt', mime_type: 'text/plain', size: 10, scan_status: 'CLEAN', folder_id: null, created_at: '2026-01-01' }
const viewer = { owner_id: 'owner', owner_username: 'Alice', owner_email: 'alice@example.com', effective_role: 'viewer', capabilities: { can_preview: true, can_download: true, can_comment: false, can_manage_access: false, can_replace: false, can_edit: false } }

async function setup(page: Page) {
  await page.addInitScript(() => { sessionStorage.setItem('cloudvault.access', 'test-access') })
  await page.route('http://localhost:8000/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/notifications/stream') return route.fulfill({ contentType: 'text/event-stream', body: ': heartbeat\n\n' })
    if (path === '/users/me/storage') return route.fulfill({ json: { used: 10, reserved: 0, limit: 100 } })
    if (path === '/folders/root') return route.fulfill({ json: { folders: [], files: [file] } })
    if (path === '/permissions/shared-with-me') return route.fulfill({ json: [{ ...viewer, permission_id: 'p1', resource_type: 'file', resource_id: 'a0', role: 'viewer', name: 'notes.txt', created_at: '2026-01-01', shared_at: '2026-01-02', recipient_username: 'Tester', recipient_email: 'tester@example.com', scan_status: 'CLEAN', mime_type: 'text/plain', size: 10, parent_id: null }] })
    if (path === '/files/a0/access') return route.fulfill({ json: viewer })
    if (path === '/files/a0/download-link') return route.fulfill({ json: { url: '/files/a0/preview', external: false, filename: 'notes.txt', mime_type: 'text/plain' } })
    if (path === '/files/a0/preview') return route.fulfill({ contentType: 'text/plain', body: 'Preview content' })
    if (path === '/files/a0/comments') return route.fulfill({ json: [] })
    return route.fulfill({ json: {} })
  })
}

test('R2 download opens a signed link without CORS or API credentials', async ({ page }) => {
  await setup(page)
  let requestHeaders: Record<string, string | string[] | undefined> = {}
  const server = createServer((request, response) => {
    requestHeaders = request.headers
    response.writeHead(200, { 'Content-Type': 'text/plain', 'Content-Disposition': 'attachment; filename="notes.txt"' })
    response.end('download works')
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  try {
    const port = (server.address() as AddressInfo).port
    await page.route('http://localhost:8000/files/a0/download-link?preview=false', (route) => route.fulfill({ json: { url: `http://127.0.0.1:${port}/signed`, external: true, filename: 'notes.txt', mime_type: 'text/plain' } }))
    await page.goto('/')
    const pending = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Download notes.txt', exact: true }).click()
    expect((await pending).suggestedFilename()).toBe('notes.txt')
    expect(requestHeaders.authorization).toBeUndefined()
    expect(requestHeaders.origin).toBeUndefined()
  } finally { await new Promise<void>((resolve) => server.close(() => resolve())) }
})

test('recipient sees sender, opens a preview, and has read-only comment controls', async ({ page }) => {
  await setup(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Shared with me', exact: true }).click()
  await expect(page.getByText('alice@example.com')).toBeVisible()
  await expect(page.getByText('Ready to preview and download')).toBeVisible()
  await page.getByRole('button', { name: 'Open preview', exact: true }).click()
  await expect(page.getByText('Preview content')).toBeVisible()
  await page.getByRole('button', { name: 'comments', exact: true }).click()
  await expect(page.getByText(/Ask the owner for Commenter/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Post comment' })).toHaveCount(0)
  await page.screenshot({ path: 'test-results/shared-preview.png', fullPage: true })
})
