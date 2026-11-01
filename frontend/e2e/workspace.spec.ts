import { createServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import { expect, test } from '@playwright/test'

const folder = { id: 'f0', name: 'Projects', parent_id: null, created_at: '2026-01-01T00:00:00Z' }
const ownerAccess = { owner_id: 'owner', owner_username: 'Owner', owner_email: 'owner@example.com', effective_role: 'owner', capabilities: { can_preview: true, can_download: true, can_comment: true, can_manage_access: true, can_replace: true, can_edit: true, can_trash: true } }
const file = { id: 'a0', original_name: 'notes.txt', mime_type: 'text/plain', size: 10, scan_status: 'CLEAN', index_status: 'READY', folder_id: null, created_at: '2026-01-01T00:00:00Z' }

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('cloudvault.access', 'test-access')
    sessionStorage.setItem('cloudvault.csrf', 'test-csrf')
  })
  await page.route('http://localhost:8000/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/notifications/stream') return route.fulfill({ contentType: 'text/event-stream', body: ': heartbeat\n\n' })
    if (path === '/users/me/storage') return route.fulfill({ json: { used: 10, reserved: 0, limit: 100, mfa_enabled: false } })
    if (path === '/folders/root') return route.fulfill({ json: { folders: [folder], files: [file] } })
    if (path === '/folders/f0/contents') return route.fulfill({ json: { folders: [], files: [] } })
    if (path === '/permissions/access' || path === '/files/a0/access') return route.fulfill({ json: ownerAccess })
    if (path === '/files/a0/download-link') return route.fulfill({ json: { url: '/files/a0/preview', external: false, mime_type: 'text/plain', filename: 'notes.txt' } })
    if (path === '/permissions') return route.fulfill({ json: [] })
    if (path === '/files/a0/preview') return route.fulfill({ contentType: 'text/plain', body: 'Preview content' })
    if (path === '/files/a0/comments') return route.fulfill({ json: route.request().method() === 'POST' ? { id: 'c1' } : [{ id: 'c1', username: 'tester', body: 'A useful comment', created_at: '2026-01-01' }] })
    if (path === '/shares') return route.fulfill({ json: [{ id: 's1', name: 'notes.txt', is_active: true, share_url: 'https://example.test/shares/test', download_count: 0 }] })
    return route.fulfill({ json: {} })
  })
})

test('folder access dialog stays open while interacting inside', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'More actions for Projects' }).click()
  await page.getByRole('button', { name: 'Manage access', exact: true }).click()
  await page.getByPlaceholder('e.g. pranav or user@example.com').click()
  await expect(page.getByRole('dialog', { name: 'Manage access' })).toBeVisible()
})

test('move uses a navigable folder picker and restores focus on escape', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'More actions for notes.txt' }).click()
  await page.getByRole('button', { name: 'Move', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Choose destination folder' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Projects' }).click()
  await expect(dialog.getByText('My files / Projects')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
})

test('file tools show comments and storage usage', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Storage: 10 B / 100 B')).toBeVisible()
  await page.getByRole('button', { name: 'More actions for notes.txt' }).click()
  await page.getByRole('button', { name: 'Open preview' }).click()
  await page.getByRole('button', { name: 'comments', exact: true }).click()
  await expect(page.getByText('A useful comment')).toBeVisible()
  await page.screenshot({ path: 'test-results/file-tools-preview.png', fullPage: true })
})

test('concurrent unauthorized requests share one refresh and keep refresh tokens out of storage', async ({ page }) => {
  let refreshes = 0
  await page.route('http://localhost:8000/auth/session/refresh', async (route) => {
    refreshes += 1
    await new Promise((resolve) => setTimeout(resolve, 100))
    await route.fulfill({ json: { access_token: 'new-access', csrf_token: 'new-csrf', token_type: 'Bearer' } })
  })
  await page.route('http://localhost:8000/test-request', async (route) => {
    if (route.request().headers().authorization === 'Bearer new-access') return route.fulfill({ json: { ok: true } })
    return route.fulfill({ status: 401, json: { detail: 'expired' } })
  })
  await page.goto('/')
  const result = await page.evaluate(async () => {
    const api = await import('/src/api.ts')
    await Promise.all([api.apiRequest('/test-request'), api.apiRequest('/test-request')])
    return sessionStorage.getItem('cloudvault.refresh')
  })
  expect(refreshes).toBe(1)
  expect(result).toBeNull()
})

test('interrupted multipart upload resumes only missing parts', async ({ page }) => {
  let partOne = 0, partTwo = 0, completions = 0, attempts = 0
  const intent = { id: 'intent-test', object_key: 'test/object', expires_at: '2026-12-01', multipart: true, chunk_size_bytes: 3, upload_url: null, multipart_upload_id: 'test-upload' }
  await page.route('http://localhost:8000/files/upload-intents', (route) => route.fulfill({ json: intent }))
  await page.route('http://localhost:8000/files/upload-intents/intent-test', (route) => route.fulfill({ json: { ...intent, completed_parts: [{ part_number: 1, etag: 'etag-one' }], already_uploaded: false } }))
  await page.route('http://localhost:8000/files/upload-intents/intent-test/parts', (route) => {
    const numbers = route.request().postDataJSON().part_numbers as number[]
    return route.fulfill({ json: { parts: numbers.map((n) => ({ part_number: n, url: `http://storage.test/part-${n}` })) } })
  })
  await page.route('http://storage.test/**', async (route) => {
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'PUT', 'Access-Control-Allow-Headers': '*' } })
    if (route.request().url().endsWith('part-1')) partOne += 1
    else { partTwo += 1; attempts += 1; if (attempts === 1) return route.abort('failed') }
    return route.fulfill({ status: 200, headers: { ETag: 'etag-test', 'Access-Control-Allow-Origin': '*', 'Access-Control-Expose-Headers': 'ETag' } })
  })
  await page.route('http://localhost:8000/files/upload-intents/intent-test/complete', (route) => { completions += 1; return route.fulfill({ json: { ...file, id: 'new-file', original_name: 'resume.txt' } }) })
  await page.goto('/')
  const upload = { name: 'resume.txt', mimeType: 'text/plain', buffer: Buffer.from('abcdef') }
  await page.locator('input[type=file]').setInputFiles(upload)
  await expect(page.getByText(/Select the same file to resume/)).toBeVisible()
  await page.locator('input[type=file]').setInputFiles(upload)
  await expect.poll(() => completions).toBe(1)
  expect(partOne).toBe(1)
  expect(partTwo).toBe(2)
})

test('signed storage download redirects without forwarding API credentials or custom headers', async ({ page }) => {
  let storageHeaders: Record<string, string | string[] | undefined> = {}
  const server = createServer((request, response) => {
    storageHeaders = request.headers
    response.writeHead(200, { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'text/plain' })
    response.end('test payload')
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  const port = (server.address() as AddressInfo).port
  try {
    await page.route('http://localhost:8000/files/a0/download', (route) => route.fulfill({
      status: 303, headers: { 'Access-Control-Allow-Origin': '*', Location: `http://127.0.0.1:${port}/download` },
    }))
    await page.goto('/')
    const body = await page.evaluate(async () => {
      const api = await import('/src/api.ts')
      return (await api.authenticatedFetch('/files/a0/download')).text()
    })
    expect(body).toBe('test payload')
    expect(storageHeaders.authorization).toBeUndefined()
    expect(storageHeaders['x-cloudvault-api']).toBeUndefined()
  } finally { await new Promise<void>((resolve) => server.close(() => resolve())) }
})
