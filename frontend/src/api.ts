import { bytesToHex } from '@noble/hashes/utils.js'
import { sha256 } from '@noble/hashes/sha2.js'

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const ACCESS_KEY = 'cloudvault.access'
const REFRESH_KEY = 'cloudvault.refresh'

export type FileItem = {
  id: string
  original_name: string
  mime_type: string
  size: number
  scan_status: 'PENDING_SCAN' | 'SCANNING' | 'CLEAN' | 'INFECTED' | string
  folder_id: string | null
  created_at: string
}

export type FolderItem = {
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
  id: string
  user_id: string
  resource_type: 'file' | 'folder'
  resource_id: string
  role: 'owner' | 'editor' | 'commenter' | 'viewer'
  created_at: string
}

export type SharedResource = {
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

type Tokens = { access_token: string; refresh_token: string; token_type: string }
type UploadIntent = {
  id: string
  object_key: string
  expires_at: string
  multipart: boolean
  chunk_size_bytes: number
  upload_url: string | null
  multipart_upload_id: string | null
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
  sessionStorage.removeItem(REFRESH_KEY)
}

function saveTokens(tokens: Tokens) {
  sessionStorage.setItem(ACCESS_KEY, tokens.access_token)
  sessionStorage.setItem(REFRESH_KEY, tokens.refresh_token)
}

async function refreshTokens(): Promise<boolean> {
  const refreshToken = sessionStorage.getItem(REFRESH_KEY)
  if (!refreshToken) return false

  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  if (!response.ok) {
    clearSession()
    return false
  }
  saveTokens((await response.json()) as Tokens)
  return true
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const run = () => {
    const headers = new Headers(init.headers)
    const token = getAccessToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }
    return fetch(`${API_BASE}${path}`, { ...init, headers })
  }

  let response = await run()
  if (response.status === 401 && await refreshTokens()) response = await run()
  if (!response.ok) throw await responseError(response)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function signIn(identifier: string, password: string) {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier, password }),
  })
  if (!response.ok) throw await responseError(response)
  saveTokens((await response.json()) as Tokens)
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
  const accessToken = sessionStorage.getItem(ACCESS_KEY)
  const refreshToken = sessionStorage.getItem(REFRESH_KEY)
  try {
    if (accessToken && refreshToken) {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
    }
  } finally {
    clearSession()
  }
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

export async function downloadFile(file: FileItem) {
  const response = await fetch(`${API_BASE}/files/${file.id}/download`, {
    headers: { Authorization: `Bearer ${getAccessToken() ?? ''}` },
  })
  if (!response.ok) throw await responseError(response)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = file.original_name
  anchor.click()
  URL.revokeObjectURL(url)
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
  const response = await fetch(`${API_BASE}/shares/${encodeURIComponent(token)}`)
  if (!response.ok) throw await responseError(response)
  return response.json() as Promise<SharePublicInfo>
}

export async function downloadSharedFile(token: string, password: string | null, filename: string) {
  const response = await fetch(`${API_BASE}/shares/${encodeURIComponent(token)}/download`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  if (!response.ok) throw await responseError(response)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
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
  file: File,
  folderId: string | null,
  onProgress: (progress: number) => void,
): Promise<FileItem | void> {
  const digest = await hashFile(file)
  let intent: UploadIntent
  try {
    intent = await apiRequest<UploadIntent>('/files/upload-intents', {
      method: 'POST',
      body: JSON.stringify({
        filename: file.name,
        mime_type: file.type || 'application/octet-stream',
        size: file.size,
        content_sha256: digest,
        folder_id: folderId,
      }),
    })
  } catch (error) {
    if (error instanceof ApiError && error.status === 503) {
      await uploadThroughApi(file, folderId, onProgress)
      return
    }
    throw error
  }

  const completedParts: { part_number: number; etag: string }[] = []

  if (!intent.multipart) {
    if (!intent.upload_url) throw new Error('Upload URL was not returned by the server.')
    await xhrUpload(
      intent.upload_url,
      file,
      {
        'Content-Type': file.type || 'application/octet-stream',
        'x-amz-meta-sha256': digest,
        'If-None-Match': '*',
      },
      (loaded) => onProgress(Math.min(99, Math.round((loaded / file.size) * 100))),
    )
  } else {
    const totalParts = Math.ceil(file.size / intent.chunk_size_bytes)
    const { parts } = await apiRequest<{ parts: { part_number: number; url: string }[] }>(
      `/files/upload-intents/${intent.id}/parts`,
      {
        method: 'POST',
        body: JSON.stringify({ part_numbers: Array.from({ length: totalParts }, (_, i) => i + 1) }),
      },
    )

    for (const part of parts) {
      const start = (part.part_number - 1) * intent.chunk_size_bytes
      const chunk = file.slice(start, Math.min(start + intent.chunk_size_bytes, file.size))
      const etag = await xhrUpload(part.url, chunk, {}, (loaded) => {
        onProgress(Math.min(99, Math.round(((start + loaded) / file.size) * 100)))
      }, true)
      if (!etag) throw new Error('Object storage did not return a part ETag. Check R2 bucket CORS.')
      completedParts.push({ part_number: part.part_number, etag })
    }
  }

  const createdFile = await apiRequest<FileItem>(`/files/upload-intents/${intent.id}/complete`, {
    method: 'POST',
    body: JSON.stringify({ parts: completedParts }),
  })
  onProgress(100)
  return createdFile
}

async function hashFile(file: File) {
  const hasher = sha256.create()
  const chunkSize = 4 * 1024 * 1024
  for (let offset = 0; offset < file.size; offset += chunkSize) {
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
): Promise<string | null> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
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

function uploadThroughApi(file: File, folderId: string | null, onProgress: (progress: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    if (folderId) form.append('folder_id', folderId)
    const request = new XMLHttpRequest()
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
      resolve()
    }
    request.onerror = () => reject(new Error('Could not reach the CloudVault API.'))
    request.send(form)
  })
}
