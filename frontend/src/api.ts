import { bytesToHex } from '@noble/hashes/utils.js'
import { sha256 } from '@noble/hashes/sha2.js'

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const ACCESS_KEY = 'cloudvault.access'
const CSRF_KEY = 'cloudvault.csrf'
let refreshInFlight: Promise<boolean> | null = null
let sessionGeneration = 0

export type AccessInfo = { owner_id: string; owner_username: string; owner_email?: string | null; effective_role: 'owner' | 'editor' | 'commenter' | 'viewer'; capabilities: Record<string, boolean> }
export type FileItem = {
  owner_username?: string | null
  effective_role?: AccessInfo['effective_role'] | null
  capabilities?: Record<string, boolean>
  id: string
  original_name: string
  mime_type: string
  size: number
  index_status?: string
  index_error?: string | null
  scan_status: 'PENDING_SCAN' | 'SCANNING' | 'CLEAN' | 'INFECTED' | string
  folder_id: string | null
  created_at: string
}

export type FolderItem = {
  owner_username?: string | null
  effective_role?: AccessInfo['effective_role'] | null
  capabilities?: Record<string, boolean>
  id: string
  name: string
  parent_id: string | null
  created_at: string
}

export type FolderContents = {
  folders: FolderItem[]
  files: FileItem[]
}

export type PermissionItem = {
  username?: string | null
  email?: string | null
  id: string
  user_id: string
  resource_type: 'file' | 'folder'
  resource_id: string
  role: 'owner' | 'editor' | 'commenter' | 'viewer'
  created_at: string
}

export type SharedResource = {
  shared_at: string
  owner_username: string
  owner_email: string | null
  recipient_username: string
  recipient_email: string | null
  effective_role: AccessInfo['effective_role']
  capabilities: Record<string, boolean>
  permission_id: string
  resource_type: 'file' | 'folder'
  resource_id: string
  role: PermissionItem['role']
  name: string
  owner_id: string
  created_at: string
  mime_type: string | null
  size: number | null
  scan_status: string | null
  parent_id: string | null
}

export type SharePublicInfo = {
  token: string
  original_name: string
  mime_type: string
  size: number
  requires_password: boolean
  expires_at: string | null
  download_count: number
  max_downloads: number | null
}


export type AuditLogItem = {
  id: string
  action: string
  details: string
  file_id: string | null
  folder_id: string | null
  created_at: string
}

export type SearchResult = FileItem & {
  score: number
  snippet: string | null
}

type Tokens = { access_token: string; csrf_token: string; token_type: string }
type UploadIntent = {
  id: string
  object_key: string
  expires_at: string
  multipart: boolean
  chunk_size_bytes: number
  upload_url: string | null
  multipart_upload_id: string | null
  completed_parts?: { part_number: number; etag: string }[]
  already_uploaded?: boolean
  completed_file?: FileItem
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function getAccessToken() {
  return sessionStorage.getItem(ACCESS_KEY)
}

export function clearSession() {
  sessionStorage.removeItem(ACCESS_KEY)
  sessionGeneration += 1
  sessionStorage.removeItem(CSRF_KEY)
  sessionStorage.removeItem('cloudvault.refresh')
}

function saveTokens(tokens: Tokens) {
  sessionStorage.setItem(ACCESS_KEY, tokens.access_token)
  sessionStorage.setItem(CSRF_KEY, tokens.csrf_token)
}

export function replaceSession(tokens: { access_token: string; csrf_token: string; token_type: string }) {
  sessionGeneration += 1
  saveTokens(tokens)
}

export function refreshTokens(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight
  const generation = sessionGeneration
  refreshInFlight = (async () => {
    const csrf = sessionStorage.getItem(CSRF_KEY)
    if (!csrf) return false
    const response = await fetch(`${API_BASE}/auth/session/refresh`, {
      method: 'POST', credentials: 'include',
      headers: { 'X-CSRF-Token': csrf },
    })
    if (generation !== sessionGeneration) return false
    if (!response.ok) { clearSession(); return false }
    saveTokens(await response.json() as Tokens)
    return true
  })().finally(() => { refreshInFlight = null })
  return refreshInFlight
}

export async function authenticatedFetch(path: string, init: RequestInit = {}) {
  const run = () => {
    const headers = new Headers(init.headers)
    const access = getAccessToken()
    if (access) headers.set('Authorization', `Bearer ${access}`)
    return fetch(`${API_BASE}${path}`, { ...init, headers, credentials: 'same-origin' })
  }
  let response = await run()
  if (response.status === 401 && await refreshTokens()) response = await run()
  if (!response.ok) throw await responseError(response)
  return response
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const run = () => {
    const headers = new Headers(init.headers)
    headers.set('X-CloudVault-API', '1')
    const token = getAccessToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }
    return fetch(`${API_BASE}${path}`, { ...init, headers, credentials: 'include' })
  }

  let response = await run()
  if (response.status === 401 && await refreshTokens()) response = await run()
  if (!response.ok) throw await responseError(response)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function signIn(identifier: string, password: string, mfaCode?: string) {
  const response = await fetch(`${API_BASE}/auth/session/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier, password, mfa_code: mfaCode || null }),
    credentials: 'include',
  })
  if (!response.ok) throw await responseError(response)
  replaceSession((await response.json()) as Tokens)
}

export async function signUp(username: string, email: string, password: string) {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email, password }),
  })
  if (!response.ok) throw await responseError(response)
  await signIn(username, password)
}

export async function signOut() {
  const csrf = sessionStorage.getItem(CSRF_KEY)
  try {
    if (csrf) await fetch(`${API_BASE}/auth/session/logout`, {
      method: 'POST', credentials: 'include',
      headers: { 'X-CSRF-Token': csrf, Authorization: `Bearer ${getAccessToken() ?? ''}` },
    })
  } finally { clearSession() }
}

function formatApiDetail(detail: unknown): string | null {
  if (typeof detail === 'string') return detail

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          const entry = item as { msg?: unknown; loc?: unknown[] }
          const location = Array.isArray(entry.loc) ? entry.loc.slice(1).join('.') : ''
          const text = typeof entry.msg === 'string' ? entry.msg : 'Invalid value'
          return location ? `${location}: ${text}` : text
        }
        return typeof item === 'string' ? item : JSON.stringify(item)
      })
      .filter(Boolean)

    return messages.join(' · ') || null
  }

  if (detail && typeof detail === 'object') {
    try {
      return JSON.stringify(detail)
    } catch {
      return 'The server rejected the request.'
    }
  }

  return null
}

async function responseError(response: Response) {
  let message = `Request failed (${response.status})`
  try {
    const body = await response.json() as { detail?: unknown }
    message = formatApiDetail(body.detail) ?? message
  } catch {
    message = response.statusText || message
  }
  return new ApiError(message, response.status)
}

export function loadFolderContents(folderId: string | null) {
  return apiRequest<FolderContents>(folderId ? `/folders/${folderId}/contents` : '/folders/root')
}

export function loadTrash() {
  return apiRequest<FileItem[]>('/files/recycle-bin')
}

export function loadSharedWithMe() {
  return apiRequest<SharedResource[]>('/permissions/shared-with-me')
}

export function loadAuditLogs() {
  return apiRequest<AuditLogItem[]>('/audit?limit=200')
}

export function createFolder(name: string, parentId: string | null) {
  return apiRequest<FolderItem>('/folders', {
    method: 'POST',
    body: JSON.stringify({ name, parent_id: parentId }),
  })
}

export function renameFolder(folderId: string, name: string) {
  return apiRequest<FolderItem>(`/folders/${folderId}`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  })
}

export function moveFolder(folderId: string, parentId: string | null) {
  return apiRequest<FolderItem>(`/folders/${folderId}/move`, {
    method: 'PATCH',
    body: JSON.stringify({ parent_id: parentId }),
  })
}

export function deleteFolder(folderId: string) {
  return apiRequest<void>(`/folders/${folderId}`, { method: 'DELETE' })
}

export function moveFile(fileId: string, folderId: string | null) {
  return apiRequest<FileItem>(`/files/${fileId}/move`, {
    method: 'PATCH',
    body: JSON.stringify({ folder_id: folderId }),
  })
}

export type DownloadLink = { url: string; external: boolean; mime_type: string; filename: string }

export function resolveFileLink(fileId: string, preview = false, signal?: AbortSignal) {
  return apiRequest<DownloadLink>(`/files/${fileId}/download-link?preview=${preview}`, { signal })
}

function saveDownload(url: string, filename: string) {
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.referrerPolicy = 'no-referrer'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}

export async function downloadFile(file: FileItem) {
  const link = await resolveFileLink(file.id)
  if (link.external) { saveDownload(link.url, link.filename); return }
  const response = await authenticatedFetch(link.url)
  const url = URL.createObjectURL(await response.blob())
  saveDownload(url, file.original_name)
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function restoreFile(fileId: string) {
  return apiRequest(`/files/${fileId}/restore`, { method: 'POST' })
}

export async function deleteFile(fileId: string, permanent = false) {
  return apiRequest(`/files/${fileId}${permanent ? '/permanent_delete' : ''}`, {
    method: 'DELETE',
  })
}

export function createShare(
  fileId: string,
  expiry: string,
  password: string,
  maxDownloads: number | null,
) {
  return apiRequest<{ share_url: string }>('/shares/share_file', {
    method: 'POST',
    body: JSON.stringify({
      file_id: fileId,
      expiry,
      password: password || null,
      max_downloads: maxDownloads,
    }),
  })
}

export async function getPublicShare(token: string) {
  const response = await fetch(`${API_BASE}/shares/${encodeURIComponent(token)}`, { headers: { 'X-CloudVault-API': '1' } })
  if (!response.ok) throw await responseError(response)
  return response.json() as Promise<SharePublicInfo>
}

export async function downloadSharedFile(token: string, password: string | null, filename: string) {
  const response = await fetch(`${API_BASE}/shares/${encodeURIComponent(token)}/download`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password, resolve: true }),
  })
  if (!response.ok) throw await responseError(response)
  if (response.headers.get('X-CloudVault-Download-Link') === '1') {
    const link = await response.json() as DownloadLink
    if (!link.external) throw new Error('The server did not return a download link.')
    saveDownload(link.url, filename)
    return
  }
  const url = URL.createObjectURL(await response.blob())
  saveDownload(url, filename)
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function getResourcePermissions(resourceType: 'file' | 'folder', resourceId: string) {
  return apiRequest<PermissionItem[]>(`/permissions?resource_type=${resourceType}&resource_id=${resourceId}`)
}

export function grantResourcePermission(
  resourceType: 'file' | 'folder',
  resourceId: string,
  targetIdentifier: string,
  role: PermissionItem['role'],
) {
  return apiRequest<PermissionItem>('/permissions', {
    method: 'POST',
    body: JSON.stringify({
      target_identifier: targetIdentifier.trim(),
      resource_type: resourceType,
      resource_id: resourceId,
      role,
    }),
  })
}

export function getPermissions(fileId: string) {
  return getResourcePermissions('file', fileId)
}

export function grantPermission(fileId: string, targetIdentifier: string, role: PermissionItem['role']) {
  return grantResourcePermission('file', fileId, targetIdentifier, role)
}

export function searchContent(
  query: string,
  limit = 20,
  signal?: AbortSignal,
) {
  return apiRequest<SearchResult[]>(
    `/search?q=${encodeURIComponent(query)}&limit=${limit}`,
    { signal },
  )
}

export function reindexAllContent() {
  return apiRequest<{ status: string; queued: number }>('/search/reindex-all', {
    method: 'POST',
  })
}

export function queueFileIndex(fileId: string) {
  return apiRequest(`/search/index/${fileId}`, { method: 'POST' })
}

export async function uploadFile(
  file: File, folderId: string | null, onProgress: (progress: number) => void,
  signal?: AbortSignal,
): Promise<FileItem> {
  const digest = await hashFile(file, signal)
  const resumeKey = `cloudvault.upload:${folderId ?? 'root'}:${digest}:${file.size}`
  let intent: UploadIntent | null = null
  const previous = sessionStorage.getItem(resumeKey)
  if (previous) {
    try {
      intent = await apiRequest<UploadIntent>(`/files/upload-intents/${previous}`, { signal })
      if (intent.completed_file) { sessionStorage.removeItem(resumeKey); onProgress(100); return intent.completed_file }
    } catch (cause) {
      if (!(cause instanceof ApiError) || ![404, 409, 410, 422].includes(cause.status)) throw cause
      sessionStorage.removeItem(resumeKey)
    }
  }
  if (!intent) {
    try {
      intent = await apiRequest<UploadIntent>('/files/upload-intents', {
        method: 'POST', signal,
        body: JSON.stringify({ filename: file.name, mime_type: file.type || 'application/octet-stream',
          size: file.size, content_sha256: digest, folder_id: folderId }),
      })
      sessionStorage.setItem(resumeKey, intent.id)
    } catch (error) {
      if (error instanceof ApiError && error.status === 503) return uploadThroughApi(file, folderId, onProgress, signal)
      throw error
    }
  }
  try {
    const completedParts = intent.completed_parts ?? []
    if (!intent.already_uploaded && !intent.multipart) {
      if (!intent.upload_url) throw new Error('Upload URL was not returned by the server.')
      await xhrUpload(intent.upload_url, file, {
        'Content-Type': file.type || 'application/octet-stream', 'x-amz-meta-sha256': digest, 'If-None-Match': '*',
      }, (loaded) => onProgress(Math.min(99, Math.round(loaded / file.size * 100))), false, signal)
    } else if (!intent.already_uploaded && intent.multipart) {
      const done = new Set(completedParts.map((p) => p.part_number))
      const count = Math.ceil(file.size / intent.chunk_size_bytes)
      const missing = Array.from({ length: count }, (_, i) => i + 1).filter((n) => !done.has(n))
      if (missing.length) {
        const { parts } = await apiRequest<{ parts: { part_number: number; url: string }[] }>(`/files/upload-intents/${intent.id}/parts`, {
          method: 'POST', signal, body: JSON.stringify({ part_numbers: missing }),
        })
        let loadedBytes = completedParts.reduce((sum, p) => sum + Math.min(intent!.chunk_size_bytes, file.size - (p.part_number - 1) * intent!.chunk_size_bytes), 0)
        for (const part of parts) {
          signal?.throwIfAborted()
          const start = (part.part_number - 1) * intent.chunk_size_bytes
          const chunk = file.slice(start, Math.min(start + intent.chunk_size_bytes, file.size))
          const etag = await xhrUpload(part.url, chunk, {}, (loaded) => onProgress(Math.min(99, Math.round((loadedBytes + loaded) / file.size * 100))), true, signal)
          if (!etag) throw new Error('Storage did not return an ETag. Check bucket CORS.')
          completedParts.push({ part_number: part.part_number, etag }); loadedBytes += chunk.size
        }
      }
    }
    const created = await apiRequest<FileItem>(`/files/upload-intents/${intent.id}/complete`, {
      method: 'POST', signal, body: JSON.stringify({ parts: intent.already_uploaded ? [] : completedParts }),
    })
    sessionStorage.removeItem(resumeKey); onProgress(100)
    return created
  } catch (cause) {
    if (signal?.aborted) {
      try {
        await apiRequest(`/files/upload-intents/${intent.id}`, { method: 'DELETE' })
        sessionStorage.removeItem(resumeKey)
      } catch { /* Preserve the session ID so cancellation can be retried after reconnecting. */ }
    }
    throw cause
  }
}

async function hashFile(file: File, signal?: AbortSignal) {
  const hasher = sha256.create()
  const chunkSize = 4 * 1024 * 1024
  for (let offset = 0; offset < file.size; offset += chunkSize) {
    signal?.throwIfAborted()
    const chunk = await file.slice(offset, offset + chunkSize).arrayBuffer()
    hasher.update(new Uint8Array(chunk))
  }
  return bytesToHex(hasher.digest())
}

function xhrUpload(
  url: string,
  body: Blob,
  headers: Record<string, string>,
  onProgress: (loaded: number) => void,
  readEtag = false,
  signal?: AbortSignal,
): Promise<string | null> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    signal?.throwIfAborted()
    const abort = () => request.abort()
    signal?.addEventListener('abort', abort, { once: true })
    request.onloadend = () => signal?.removeEventListener('abort', abort)
    request.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'))
    request.open('PUT', url)
    for (const [name, value] of Object.entries(headers)) request.setRequestHeader(name, value)
    request.upload.onprogress = (event) => onProgress(event.loaded)
    request.onload = () => {
      if (request.status < 200 || request.status >= 300) {
        reject(new Error(`Object storage upload failed (${request.status}).`))
        return
      }
      resolve(readEtag ? request.getResponseHeader('ETag') : null)
    }
    request.onerror = () => reject(new Error('Could not reach object storage. Check bucket CORS settings.'))
    request.send(body)
  })
}

function uploadThroughApi(file: File, folderId: string | null, onProgress: (progress: number) => void, signal?: AbortSignal) {
  return new Promise<FileItem>((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    if (folderId) form.append('folder_id', folderId)
    const request = new XMLHttpRequest()
    signal?.throwIfAborted()
    const abort = () => request.abort()
    signal?.addEventListener('abort', abort, { once: true })
    request.onloadend = () => signal?.removeEventListener('abort', abort)
    request.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'))
    request.open('POST', `${API_BASE}/files/upload`)
    request.setRequestHeader('Authorization', `Bearer ${getAccessToken() ?? ''}`)
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100))
    }
    request.onload = () => {
      if (request.status < 200 || request.status >= 300) {
        try {
          reject(new ApiError(JSON.parse(request.responseText).detail ?? 'Upload failed.', request.status))
        } catch {
          reject(new ApiError('Upload failed.', request.status))
        }
        return
      }
      onProgress(100)
      resolve(JSON.parse(request.responseText) as FileItem)
    }
    request.onerror = () => reject(new Error('Could not reach the CloudVault API.'))
    request.send(form)
  })
}
