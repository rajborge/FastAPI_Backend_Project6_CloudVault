import { startTransition, useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import {
  ArchiveRestore,
  Check,
  ChevronRight,
  CircleUserRound,
  Clock3,
  Copy,
  Download,
  FileImage,
  FileText,
  FolderClosed,
  HardDrive,
  Home,
  LoaderCircle,
  LogOut,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Share2,
  ShieldCheck,
  Trash2,
  Upload,
  UsersRound,
  X,
} from 'lucide-react'
import {
  ApiError,
  apiRequest,
  clearSession,
  deleteFolder,
  createFolder,
  createShare,
  deleteFile,
  downloadFile,
  getAccessToken,
  getResourcePermissions,
  grantResourcePermission,
  loadSharedWithMe,
  loadAuditLogs,
  loadFolderContents,
  loadTrash,
  moveFile,
  moveFolder,
  renameFolder,
  restoreFile,
  searchContent,
  signIn,
  signOut,
  signUp,
  uploadFile,
  type FileItem,
  type FolderContents,
  type FolderItem,
  type PermissionItem,
  type SharedResource,
  type AuditLogItem,
  type SearchResult,
} from './api'
import './App.css'

type View = 'files' | 'shared' | 'activity' | 'trash'
type Transfer = { id: string; name: string; progress: number; status: 'uploading' | 'scanning' | 'done' | 'error'; message?: string }

const emptyContents: FolderContents = { folders: [], files: [] }

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[index]}`
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value))
}

function fileIcon(file: FileItem) {
  return file.mime_type.startsWith('image/') ? <FileImage size={18} /> : <FileText size={18} />
}

function cleanSearchSnippet(value: string | null) {
  if (!value) return ''
  return value.replace(/<\/?b>/gi, '').replace(/\s+/g, ' ').trim()
}

function App() {
  const [token, setToken] = useState(() => getAccessToken())
  const [identity, setIdentity] = useState(() => sessionStorage.getItem('cloudvault.identity') ?? '')
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [authError, setAuthError] = useState('')
  const [authBusy, setAuthBusy] = useState(false)
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [view, setView] = useState<View>('files')
  const [contents, setContents] = useState<FolderContents>(emptyContents)
  const [trash, setTrash] = useState<FileItem[]>([])
  const [sharedResources, setSharedResources] = useState<SharedResource[]>([])
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([])
  const [folderStack, setFolderStack] = useState<FolderItem[]>([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [searchBusy, setSearchBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [transfers, setTransfers] = useState<Transfer[]>([])
  const [folderDialog, setFolderDialog] = useState(false)
  const [folderName, setFolderName] = useState('')
  const [shareFile, setShareFile] = useState<FileItem | null>(null)
  const [shareExpiry, setShareExpiry] = useState('7_days')
  const [sharePassword, setSharePassword] = useState('')
  const [shareLimit, setShareLimit] = useState('')
  const [permissionFile, setPermissionFile] = useState<FileItem | null>(null)
  const [permissionFolder, setPermissionFolder] = useState<FolderItem | null>(null)
  const [permissions, setPermissions] = useState<PermissionItem[]>([])
  const [permissionUserId, setPermissionUserId] = useState('')
  const [permissionRole, setPermissionRole] = useState<PermissionItem['role']>('viewer')
  const [actionBusy, setActionBusy] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const currentFolder = folderStack.at(-1) ?? null
  const normalizedSearch = search.trim()
  const intelligentSearchActive = view === 'files' && normalizedSearch.length >= 2
  const visibleFiles = contents.files
  const visibleFolders = contents.folders
  const visibleTrash = trash.filter((file) => file.original_name.toLowerCase().includes(search.toLowerCase()))
  const visibleShared = sharedResources.filter((resource) => resource.name.toLowerCase().includes(search.toLowerCase()))
  const visibleAudit = auditLogs.filter((entry) => `${entry.action} ${entry.details}`.toLowerCase().includes(search.toLowerCase()))

  const reload = useCallback(async (showSpinner = true) => {
    if (!token) return
    if (showSpinner) {
      setLoading(true)
      setError('')
    }
    try {
      if (view === 'trash') {
        const files = await loadTrash()
        startTransition(() => setTrash(files))
      } else if (view === 'shared') {
        const resources = await loadSharedWithMe()
        startTransition(() => setSharedResources(resources))
      } else if (view === 'activity') {
        const entries = await loadAuditLogs()
        startTransition(() => setAuditLogs(entries))
      } else {
        const folderContents = await loadFolderContents(currentFolder?.id ?? null)
        startTransition(() => setContents(folderContents))
      }
    } catch (cause) {
      startTransition(() => {
        setError(cause instanceof Error ? cause.message : 'Could not load files.')
        if (cause instanceof ApiError && cause.status === 401) handleSessionExpired()
      })
    } finally {
      if (showSpinner) startTransition(() => setLoading(false))
    }
  }, [token, view, currentFolder?.id])

  useEffect(() => {
    if (token) startTransition(() => { void reload(false) })
  }, [token, view, currentFolder?.id, reload])


  useEffect(() => {
    if (!token || view !== 'files') {
      setSearchResults([])
      setSearchBusy(false)
      return
    }

    const query = search.trim()
    if (query.length < 2) {
      setSearchResults([])
      setSearchBusy(false)
      return
    }

    const controller = new AbortController()
    const timeout = window.setTimeout(async () => {
      setSearchBusy(true)
      try {
        const results = await searchContent(query, 20, controller.signal)
        if (!controller.signal.aborted) {
          startTransition(() => setSearchResults(results))
        }
      } catch (cause) {
        if (cause instanceof DOMException && cause.name === 'AbortError') return
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : 'Search failed.')
        }
      } finally {
        if (!controller.signal.aborted) setSearchBusy(false)
      }
    }, 350)

    return () => {
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [search, token, view])

  useEffect(() => {
    if (!token || view !== 'files') return
    const needsPolling = contents.files.some((file) => file.scan_status === 'PENDING_SCAN' || file.scan_status === 'SCANNING')
    if (!needsPolling) return
    const timer = window.setInterval(() => { void reload(false) }, 2000)
    return () => window.clearInterval(timer)
  }, [token, view, contents.files, reload])

  useEffect(() => {
    const cleanNames = new Set(contents.files.filter((file) => file.scan_status === 'CLEAN').map((file) => file.original_name))
    if (cleanNames.size === 0) return
    setTransfers((items) => items.map((item) => item.status === 'scanning' && cleanNames.has(item.name)
      ? { ...item, status: 'done', message: 'Ready' }
      : item))
  }, [contents.files])

  function notify(text: string) {
    setMessage(text)
    window.setTimeout(() => setMessage(''), 3200)
  }

  function handleSessionExpired() {
    clearSession()
    sessionStorage.removeItem('cloudvault.identity')
    setToken(null)
    setIdentity('')
    setFolderStack([])
    setContents(emptyContents)
  }

  async function handleSignOut() {
    await signOut()
    handleSessionExpired()
  }

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setAuthBusy(true)
    setAuthError('')
    try {
      if (authMode === 'register') {
        await signUp(username, email, password)
        sessionStorage.setItem('cloudvault.identity', username)
        setIdentity(username)
      } else {
        await signIn(email || username, password)
        const label = email || username
        sessionStorage.setItem('cloudvault.identity', label)
        setIdentity(label)
      }
      setToken(getAccessToken())
      setPassword('')
    } catch (cause) {
      setAuthError(cause instanceof Error ? cause.message : 'Could not authenticate.')
    } finally {
      setAuthBusy(false)
    }
  }

  async function handleCreateFolder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!folderName.trim()) return
    setActionBusy(true)
    try {
      await createFolder(folderName.trim(), currentFolder?.id ?? null)
      setFolderName('')
      setFolderDialog(false)
      await reload()
      notify('Folder created')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not create folder.')
    } finally {
      setActionBusy(false)
    }
  }

  async function handleFilesSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    for (const file of files) {
      const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`
      setTransfers((items) => [...items, { id, name: file.name, progress: 0, status: 'uploading' }])
      try {
        await uploadFile(file, currentFolder?.id ?? null, (progress) => {
          setTransfers((items) => items.map((item) => item.id === id ? { ...item, progress } : item))
        })
        setTransfers((items) => items.map((item) => item.id === id ? { ...item, progress: 100, status: 'scanning' } : item))
      } catch (cause) {
        setTransfers((items) => items.map((item) => item.id === id ? {
          ...item,
          status: 'error',
          message: cause instanceof Error ? cause.message : 'Upload failed',
        } : item))
      }
    }
    await reload()
  }

  async function handleDownload(file: FileItem) {
    try {
      await downloadFile(file)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Download failed.')
    }
  }

  async function handleTrash(file: FileItem) {
    try {
      await deleteFile(file.id)
      await reload()
      notify('Moved to trash')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not move file to trash.')
    }
  }

  async function handleRestore(file: FileItem) {
    try {
      await restoreFile(file.id)
      await reload()
      notify('File restored')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not restore file.')
    }
  }

  async function handlePermanentDelete(file: FileItem) {
    if (!window.confirm(`Permanently delete ${file.original_name}? This cannot be undone.`)) return
    try {
      await deleteFile(file.id, true)
      await reload()
      notify('File permanently deleted')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not delete file.')
    }
  }

  async function handleRenameFolder(folder: FolderItem) {
    const nextName = window.prompt('New folder name', folder.name)?.trim()
    if (!nextName || nextName === folder.name) return
    try {
      await renameFolder(folder.id, nextName)
      await reload()
      notify('Folder renamed')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not rename folder.')
    }
  }

  async function handleMoveFolder(folder: FolderItem) {
    const destination = window.prompt('Destination folder UUID. Leave blank for root.', '')
    if (destination === null) return
    try {
      await moveFolder(folder.id, destination.trim() || null)
      await reload()
      notify('Folder moved')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not move folder.')
    }
  }

  async function handleDeleteFolder(folder: FolderItem) {
    if (!window.confirm(`Delete ${folder.name}? Files inside it will be moved to Trash.`)) return
    try {
      await deleteFolder(folder.id)
      await reload()
      notify('Folder deleted; contained files moved to Trash')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not delete folder.')
    }
  }

  async function handleMoveFile(file: FileItem) {
    const destination = window.prompt('Destination folder UUID. Leave blank for root.', '')
    if (destination === null) return
    try {
      await moveFile(file.id, destination.trim() || null)
      await reload()
      notify('File moved')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not move file.')
    }
  }

  function openSharedResource(resource: SharedResource) {
    if (resource.resource_type === 'folder') {
      setView('files')
      setFolderStack([{ id: resource.resource_id, name: resource.name, parent_id: resource.parent_id, created_at: resource.created_at }])
      return
    }
    const file: FileItem = {
      id: resource.resource_id,
      original_name: resource.name,
      mime_type: resource.mime_type ?? 'application/octet-stream',
      size: resource.size ?? 0,
      scan_status: resource.scan_status ?? 'CLEAN',
      folder_id: resource.parent_id,
      created_at: resource.created_at,
    }
    void handleDownload(file)
  }

  async function handleShare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!shareFile) return
    setActionBusy(true)
    try {
      const result = await createShare(
        shareFile.id,
        shareExpiry,
        sharePassword,
        shareLimit ? Number(shareLimit) : null,
      )
      await navigator.clipboard.writeText(result.share_url)
      setShareFile(null)
      setSharePassword('')
      setShareLimit('')
      notify('Share link copied')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not create share link.')
    } finally {
      setActionBusy(false)
    }
  }

  async function handleGrantPermission(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const resourceType = permissionFolder ? 'folder' : 'file'
    const resourceId = permissionFolder?.id ?? permissionFile?.id
    const targetIdentifier = permissionUserId.trim()
    if (!resourceId || !targetIdentifier) return
    setError('')
    setActionBusy(true)
    try {
      await grantResourcePermission(resourceType, resourceId, targetIdentifier, permissionRole)
      setPermissionUserId('')
      setPermissions(await getResourcePermissions(resourceType, resourceId))
      notify('Access updated')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not update access.')
    } finally {
      setActionBusy(false)
    }
  }

  async function openPermissionManager(file: FileItem) {
    setPermissionFolder(null)
    setPermissionFile(file)
    setPermissions([])
    try {
      setPermissions(await getResourcePermissions('file', file.id))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load permissions.')
    }
  }

  async function openFolderPermissionManager(folder: FolderItem) {
    setPermissionFile(null)
    setPermissionFolder(folder)
    setPermissions([])
    try {
      setPermissions(await getResourcePermissions('folder', folder.id))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load permissions.')
    }
  }

  async function revokePermission(permissionId: string) {
    const resourceType = permissionFolder ? 'folder' : 'file'
    const resourceId = permissionFolder?.id ?? permissionFile?.id
    if (!resourceId) return
    try {
      await apiRequest(`/permissions/${permissionId}`, { method: 'DELETE' })
      setPermissions(await getResourcePermissions(resourceType, resourceId))
      notify('Access removed')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not remove access.')
    }
  }

  if (!token) {
    return (
      <main className="auth-page">
        <div className="auth-brand"><span className="brand-mark"><HardDrive size={21} /></span><span>cloudvault</span></div>
        <section className="auth-layout">
          <div className="auth-copy">
            <p className="eyebrow">YOUR FILES, IN THEIR PLACE</p>
            <h1>A quieter way to keep everything.</h1>
            <p className="auth-intro">A private workspace for the documents, images, and ideas you need close at hand.</p>
            <div className="auth-assurance"><ShieldCheck size={18} /><span>Uploads are scanned before they become available.</span></div>
          </div>
          <form className="auth-form" onSubmit={submitAuth}>
            <div className="auth-form-heading">
              <p className="eyebrow">CLOUDVAULT ACCOUNT</p>
              <h2>{authMode === 'login' ? 'Welcome back' : 'Create your account'}</h2>
              <p>{authMode === 'login' ? 'Sign in to continue to your files.' : 'Start with a free 5 GB workspace.'}</p>
            </div>
            {authMode === 'register' && <label>Username<input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} /></label>}
            {authMode === 'register' ? (
              <label>Email<input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
            ) : (
              <label>Email or username<input autoComplete="username" value={email || username} onChange={(event) => { setEmail(event.target.value); setUsername(event.target.value) }} required /></label>
            )}
            <label>Password<input type="password" autoComplete={authMode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} /></label>
            {authError && <p className="form-error" role="alert">{authError}</p>}
            <button className="button button-primary auth-submit" type="submit" disabled={authBusy}>
              {authBusy ? <LoaderCircle className="spin" size={17} /> : null}
              {authMode === 'login' ? 'Sign in' : 'Create account'}
            </button>
            <p className="auth-switch">
              {authMode === 'login' ? 'New to CloudVault?' : 'Already have an account?'}{' '}
              <button type="button" onClick={() => { setAuthMode(authMode === 'login' ? 'register' : 'login'); setAuthError('') }}>
                {authMode === 'login' ? 'Create an account' : 'Sign in'}
              </button>
            </p>
          </form>
        </section>
        <footer className="auth-footer"><span>CloudVault</span><span>Private storage, thoughtfully managed.</span></footer>
      </main>
    )
  }

  return (
    <div className="workspace-shell">
      <aside className="sidebar">
        <a className="brand" href="#files" onClick={(event) => { event.preventDefault(); setView('files'); setFolderStack([]) }}>
          <span className="brand-mark"><HardDrive size={20} /></span><span>cloudvault</span>
        </a>
        <button className="button button-primary sidebar-upload" onClick={() => fileInput.current?.click()}><Upload size={17} /> Upload files</button>
        <input ref={fileInput} className="visually-hidden" type="file" multiple onChange={handleFilesSelected} />
        <nav className="side-nav" aria-label="Main navigation">
          <p className="nav-label">WORKSPACE</p>
          <button className={`nav-item ${view === 'files' ? 'selected' : ''}`} onClick={() => { setView('files'); setFolderStack([]) }}><Home size={17} /><span>My files</span><span className="nav-count">{contents.files.length}</span></button>
          <button className={`nav-item ${view === 'shared' ? 'selected' : ''}`} onClick={() => { setView('shared'); setFolderStack([]) }}><UsersRound size={17} /><span>Shared with me</span></button>
          <button className={`nav-item ${view === 'activity' ? 'selected' : ''}`} onClick={() => { setView('activity'); setFolderStack([]) }}><Clock3 size={17} /><span>Activity</span></button>
          <button className={`nav-item ${view === 'trash' ? 'selected' : ''}`} onClick={() => { setView('trash'); setFolderStack([]) }}><Trash2 size={17} /><span>Trash</span></button>
        </nav>
        <div className="sidebar-spacer" />
        <div className="security-note"><span className="security-icon"><ShieldCheck size={16} /></span><div><strong>Protected uploads</strong><span>Scanned before access</span></div></div>
        <div className="account-row">
          <span className="avatar"><CircleUserRound size={18} /></span>
          <span className="account-name" title={identity}>{identity || 'Your account'}</span>
          <button className="icon-button account-logout" title="Sign out" aria-label="Sign out" onClick={() => void handleSignOut()}><LogOut size={16} /></button>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div className="breadcrumb" aria-label="Breadcrumb">
            <button onClick={() => { setView('files'); setFolderStack([]) }} className="crumb-root">My files</button>
            {view === 'files' && folderStack.map((folder, index) => (
              <span className="crumb-part" key={folder.id}><ChevronRight size={14} /><button onClick={() => setFolderStack((stack) => stack.slice(0, index + 1))}>{folder.name}</button></span>
            ))}
            {view === 'shared' && <span className="crumb-part"><ChevronRight size={14} /><span>Shared with me</span></span>}
            {view === 'activity' && <span className="crumb-part"><ChevronRight size={14} /><span>Activity</span></span>}
            {view === 'trash' && <span className="crumb-part"><ChevronRight size={14} /><span>Trash</span></span>}
          </div>
          <div className="topbar-tools">
            <label className="search-box">{searchBusy && view === 'files' ? <LoaderCircle className="spin" size={16} /> : <Search size={16} />}<input aria-label="Search file names and contents" placeholder={view === 'files' ? 'Search files and contents…' : `Search ${view}…`} value={search} onChange={(event) => setSearch(event.target.value)} />{search ? <button type="button" className="search-clear" aria-label="Clear search" onClick={() => setSearch('')}><X size={14} /></button> : <kbd>/</kbd>}</label>
            <button className="icon-button refresh-button" title="Refresh" aria-label="Refresh" onClick={() => void reload()}><Clock3 size={17} /></button>
          </div>
        </header>

        <section className="content-area">
          <div className="page-heading">
            <div>
              <p className="eyebrow">{view === 'trash' ? 'RECYCLE BIN' : view === 'shared' ? 'COLLABORATION' : view === 'activity' ? 'AUDIT TRAIL' : currentFolder ? 'FOLDER' : 'YOUR SPACE'}</p>
              <h1>{view === 'trash' ? 'Trash' : view === 'shared' ? 'Shared with me' : view === 'activity' ? 'Activity' : currentFolder?.name ?? 'My files'}</h1>
              <p className="page-subtitle">{view === 'trash' ? 'Deleted files are permanently removed after 30 days.' : view === 'shared' ? `${sharedResources.length} shared items` : view === 'activity' ? `${auditLogs.length} recorded events` : `${contents.folders.length} folders · ${contents.files.length} files`}</p>
            </div>
            {view === 'files' && <div className="heading-actions"><button className="button button-secondary" onClick={() => setFolderDialog(true)}><Plus size={17} /> New folder</button><button className="button button-primary heading-upload" onClick={() => fileInput.current?.click()}><Upload size={17} /> Upload</button></div>}
          </div>

          {(error || message) && <div className={`notice ${error ? 'notice-error' : 'notice-success'}`} role={error ? 'alert' : 'status'}>
            {error ? <X size={16} /> : <Check size={16} />}
            <span>{error || message}</span>
            {error && <button className="notice-close" aria-label="Dismiss" onClick={() => setError('')}><X size={15} /></button>}
          </div>}

          {view === 'files' ? (
            intelligentSearchActive ? (
              <div className="file-table-wrap search-results-wrap">
                <div className="table-toolbar">
                  <span className="table-meta">
                    {searchBusy ? <><LoaderCircle className="spin" size={15} /> Searching file contents…</> : <><strong>{searchResults.length}</strong> results for “{normalizedSearch}”</>}
                  </span>
                  <span className="search-scope-label">PDF · TXT · OCR images</span>
                </div>
                {searchBusy && searchResults.length === 0 ? (
                  <div className="loading-state"><LoaderCircle className="spin" size={22} /><span>Searching filenames, PDF text and OCR content…</span></div>
                ) : searchResults.length === 0 ? (
                  <div className="empty-state"><div className="empty-art"><Search size={28} /></div><h2>No content matches</h2><p>No indexed file matched “{normalizedSearch}”. Try another phrase or wait for scanning/indexing to finish.</p></div>
                ) : (
                  <div className="search-result-list">
                    {searchResults.map((file) => (
                      <div className="search-result-card" key={file.id}>
                        <div className="search-result-icon">{fileIcon(file)}</div>
                        <div className="search-result-content">
                          <div className="search-result-title-row">
                            <strong title={file.original_name}>{file.original_name}</strong>
                            <span className={`match-chip ${file.score >= 0.999 ? 'exact' : ''}`}>{file.score >= 0.999 ? 'Exact match' : 'Content match'}</span>
                          </div>
                          {file.snippet && <p className="search-result-snippet">{cleanSearchSnippet(file.snippet)}</p>}
                          <div className="search-result-meta"><span>{file.mime_type}</span><span>·</span><span>{formatBytes(file.size)}</span><span>·</span><span>{formatDate(file.created_at)}</span><span>·</span><span>{file.scan_status === 'CLEAN' ? 'Ready' : file.scan_status}</span></div>
                        </div>
                        <div className="search-result-actions">
                          <button className="icon-button row-action" title="Download" aria-label={`Download ${file.original_name}`} disabled={file.scan_status !== 'CLEAN'} onClick={() => void handleDownload(file)}><Download size={16} /></button>
                          <button className="icon-button row-action" title="Share" aria-label={`Share ${file.original_name}`} onClick={() => { setShareFile(file); setShareExpiry('7_days') }}><Share2 size={16} /></button>
                          <details className="action-menu"><summary className="icon-button row-action" aria-label={`More actions for ${file.original_name}`}><MoreHorizontal size={17} /></summary><div className="menu-popover"><button onClick={() => void openPermissionManager(file)}><UsersRound size={15} /> Manage access</button><button onClick={() => void handleMoveFile(file)}><FolderClosed size={15} /> Move</button><button className="danger-item" onClick={() => void handleTrash(file)}><Trash2 size={15} /> Move to trash</button></div></details>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="file-table-wrap">
                <div className="table-toolbar"><span className="table-meta"><strong>{visibleFolders.length + visibleFiles.length}</strong> items</span><div className="table-column-head"><span>Name</span><span>Last modified</span><span>Size</span><span>Status</span><span /></div></div>
                {loading ? <div className="loading-state"><LoaderCircle className="spin" size={22} /><span>Loading your files</span></div> : visibleFolders.length + visibleFiles.length === 0 ? (
                  <div className="empty-state"><div className="empty-art"><FolderClosed size={28} /></div><h2>A little room to begin</h2><p>Create a folder or upload a file to get your workspace started.</p><div className="empty-actions"><button className="button button-secondary" onClick={() => setFolderDialog(true)}><Plus size={16} /> New folder</button><button className="button button-primary" onClick={() => fileInput.current?.click()}><Upload size={16} /> Upload a file</button></div></div>
                ) : (
                  <div className="file-list">
                    {visibleFolders.map((folder) => <div className="file-row folder-row" key={folder.id} role="button" tabIndex={0} onClick={() => setFolderStack((stack) => [...stack, folder])} onKeyDown={(event) => { if (event.key === 'Enter') setFolderStack((stack) => [...stack, folder]) }}>
                      <div className="file-name-cell"><span className="file-type folder-type"><FolderClosed size={18} /></span><span className="file-title">{folder.name}</span></div><span className="file-date">{formatDate(folder.created_at)}</span><span className="file-size">—</span><span className="file-status"><span className="status-text">Folder</span><ChevronRight className="folder-arrow" size={16} /></span><span className="file-actions" onClick={(event) => event.stopPropagation()}><details className="action-menu"><summary className="icon-button row-action" aria-label={`More actions for ${folder.name}`}><MoreHorizontal size={17} /></summary><div className="menu-popover"><button onClick={() => void handleRenameFolder(folder)}><Pencil size={15} /> Rename</button><button onClick={() => void handleMoveFolder(folder)}><FolderClosed size={15} /> Move</button><button onClick={() => void openFolderPermissionManager(folder)}><UsersRound size={15} /> Manage access</button><button className="danger-item" onClick={() => void handleDeleteFolder(folder)}><Trash2 size={15} /> Delete folder</button></div></details></span>
                    </div>)}
                    {visibleFiles.map((file) => <div className="file-row" key={file.id}>
                      <div className="file-name-cell"><span className="file-type">{fileIcon(file)}</span><span className="file-title" title={file.original_name}>{file.original_name}</span></div>
                      <span className="file-date">{formatDate(file.created_at)}</span><span className="file-size">{formatBytes(file.size)}</span>
                      <span className="file-status"><span className={`status-dot ${file.scan_status.toLowerCase()}`} />{file.scan_status === 'PENDING_SCAN' ? 'Queued' : file.scan_status === 'SCANNING' ? 'Scanning' : file.scan_status === 'CLEAN' ? 'Ready' : file.scan_status}</span>
                      <span className="file-actions">
                        <button className="icon-button row-action" title="Download" aria-label={`Download ${file.original_name}`} disabled={file.scan_status !== 'CLEAN'} onClick={() => void handleDownload(file)}><Download size={16} /></button>
                        <details className="action-menu"><summary className="icon-button row-action" aria-label={`More actions for ${file.original_name}`}><MoreHorizontal size={17} /></summary><div className="menu-popover"><button onClick={() => { setShareFile(file); setShareExpiry('7_days') }}><Share2 size={15} /> Create share link</button><button onClick={() => void openPermissionManager(file)}><UsersRound size={15} /> Manage access</button><button onClick={() => { const nextName = window.prompt('New file name', file.original_name); if (nextName?.trim()) void apiRequest(`/files/${file.id}/rename`, { method: 'PATCH', body: JSON.stringify({ name: nextName.trim() }) }).then(() => reload()).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'Rename failed.')) }}><Pencil size={15} /> Rename</button><button onClick={() => void handleMoveFile(file)}><FolderClosed size={15} /> Move</button><button className="danger-item" onClick={() => void handleTrash(file)}><Trash2 size={15} /> Move to trash</button></div></details>
                      </span>
                    </div>)}
                  </div>
                )}
              </div>
            )
          ) : view === 'shared' ? (
            <div className="file-table-wrap">
              <div className="table-toolbar"><span className="table-meta"><strong>{visibleShared.length}</strong> shared items</span><div className="table-column-head"><span>Name</span><span>Shared</span><span>Role</span><span>Type</span><span /></div></div>
              {loading ? <div className="loading-state"><LoaderCircle className="spin" size={22} /><span>Loading shared items</span></div> : visibleShared.length === 0 ? <div className="empty-state"><div className="empty-art"><UsersRound size={27} /></div><h2>Nothing shared with you yet</h2><p>Folders and files shared directly with your account will appear here.</p></div> : <div className="file-list">{visibleShared.map((resource) => <div className="file-row" key={resource.permission_id}><div className="file-name-cell"><span className="file-type">{resource.resource_type === 'folder' ? <FolderClosed size={18} /> : <FileText size={18} />}</span><span className="file-title">{resource.name}</span></div><span className="file-date">{formatDate(resource.created_at)}</span><span className="file-size">{resource.role}</span><span className="file-status">{resource.resource_type}</span><span className="file-actions"><button className="button button-secondary" onClick={() => openSharedResource(resource)}>{resource.resource_type === 'folder' ? 'Open' : 'Download'}</button></span></div>)}</div>}
            </div>
          ) : view === 'activity' ? (
            <div className="file-table-wrap">
              <div className="table-toolbar"><span className="table-meta"><strong>{visibleAudit.length}</strong> events</span><div className="table-column-head"><span>Action</span><span>Time</span><span>Details</span><span>Resource</span><span /></div></div>
              {loading ? <div className="loading-state"><LoaderCircle className="spin" size={22} /><span>Loading activity</span></div> : visibleAudit.length === 0 ? <div className="empty-state"><div className="empty-art"><Clock3 size={27} /></div><h2>No activity yet</h2><p>File and folder actions will appear here.</p></div> : <div className="file-list">{visibleAudit.map((entry) => <div className="file-row" key={entry.id}><div className="file-name-cell"><span className="file-type"><Clock3 size={18} /></span><span className="file-title">{entry.action.replaceAll('_', ' ')}</span></div><span className="file-date">{formatDate(entry.created_at)}</span><span className="file-size" title={entry.details}>{entry.details}</span><span className="file-status">{entry.file_id ? 'File' : entry.folder_id ? 'Folder' : 'Account'}</span><span className="file-actions" /></div>)}</div>}
            </div>
          ) : (
            <div className="file-table-wrap">
              <div className="table-toolbar"><span className="table-meta"><strong>{visibleTrash.length}</strong> items</span><div className="table-column-head"><span>Name</span><span>Deleted</span><span>Size</span><span>Retention</span><span /></div></div>
              {loading ? <div className="loading-state"><LoaderCircle className="spin" size={22} /><span>Loading trash</span></div> : visibleTrash.length === 0 ? <div className="empty-state"><div className="empty-art"><Trash2 size={27} /></div><h2>Trash is empty</h2><p>Files you delete will appear here before permanent removal.</p></div> : <div className="file-list">{visibleTrash.map((file) => <div className="file-row" key={file.id}><div className="file-name-cell"><span className="file-type">{fileIcon(file)}</span><span className="file-title">{file.original_name}</span></div><span className="file-date">{formatDate(file.created_at)}</span><span className="file-size">{formatBytes(file.size)}</span><span className="file-status retention-label"><Clock3 size={14} /> 30 days</span><span className="file-actions"><button className="icon-button row-action" title="Restore" aria-label={`Restore ${file.original_name}`} onClick={() => void handleRestore(file)}><ArchiveRestore size={16} /></button><button className="icon-button row-action danger-action" title="Permanently delete" aria-label={`Permanently delete ${file.original_name}`} onClick={() => void handlePermanentDelete(file)}><Trash2 size={16} /></button></span></div>)}</div>}
            </div>
          )}
          <footer className="workspace-foot"><span><ShieldCheck size={14} /> Files are scanned before download</span><span>CloudVault · Private storage</span></footer>
        </section>
      </main>

      {transfers.length > 0 && <aside className="transfer-panel" aria-label="Upload activity"><div className="transfer-heading"><div><span className="transfer-icon"><Upload size={15} /></span><strong>Transfers</strong></div><button className="icon-button" aria-label="Dismiss transfers" onClick={() => setTransfers([])}><X size={16} /></button></div>{transfers.map((transfer) => <div className="transfer-row" key={transfer.id}><div className="transfer-file"><span className="transfer-name">{transfer.name}</span><span className={`transfer-state ${transfer.status}`}>{transfer.status === 'uploading' ? `${transfer.progress}%` : transfer.status === 'scanning' ? 'Scanning' : transfer.message}</span></div><div className="progress-track"><span style={{ width: `${transfer.progress}%` }} /></div></div>)}</aside>}

      {folderDialog && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setFolderDialog(false) }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="folder-title"><div className="modal-head"><div><p className="eyebrow">ORGANIZE</p><h2 id="folder-title">New folder</h2></div><button className="icon-button" aria-label="Close" onClick={() => setFolderDialog(false)}><X size={18} /></button></div><form onSubmit={handleCreateFolder}><label>Folder name<input autoFocus value={folderName} onChange={(event) => setFolderName(event.target.value)} maxLength={255} required /></label><div className="modal-actions"><button type="button" className="button button-secondary" onClick={() => setFolderDialog(false)}>Cancel</button><button className="button button-primary" disabled={actionBusy}>{actionBusy ? 'Creating…' : 'Create folder'}</button></div></form></section></div>}

      {shareFile && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setShareFile(null) }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="share-title"><div className="modal-head"><div><p className="eyebrow">SECURE SHARING</p><h2 id="share-title">Share file</h2><p className="modal-file-name">{shareFile.original_name}</p></div><button className="icon-button" aria-label="Close" onClick={() => setShareFile(null)}><X size={18} /></button></div><form onSubmit={handleShare}><label>Link expires<select value={shareExpiry} onChange={(event) => setShareExpiry(event.target.value)}><option value="never">Never</option><option value="1_day">After 1 day</option><option value="7_days">After 7 days</option><option value="30_days">After 30 days</option></select></label><label>Password <span className="optional-label">Optional</span><input type="password" autoComplete="new-password" value={sharePassword} onChange={(event) => setSharePassword(event.target.value)} /></label><label>Download limit <span className="optional-label">Optional</span><input type="number" min="1" value={shareLimit} onChange={(event) => setShareLimit(event.target.value)} placeholder="Unlimited" /></label><div className="modal-actions"><button type="button" className="button button-secondary" onClick={() => setShareFile(null)}>Cancel</button><button className="button button-primary" disabled={actionBusy}><Copy size={15} />{actionBusy ? 'Creating…' : 'Create & copy link'}</button></div></form></section></div>}

      {(permissionFile || permissionFolder) && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setPermissionFile(null); setPermissionFolder(null) }}><section className="modal permission-modal" role="dialog" aria-modal="true" aria-labelledby="access-title"><div className="modal-head"><div><p className="eyebrow">{permissionFolder ? 'FOLDER ACCESS' : 'FILE ACCESS'}</p><h2 id="access-title">Manage access</h2><p className="modal-file-name">{permissionFolder?.name ?? permissionFile?.original_name}</p></div><button className="icon-button" aria-label="Close" onClick={() => { setPermissionFile(null); setPermissionFolder(null) }}><X size={18} /></button></div><form onSubmit={handleGrantPermission} className="grant-form"><label>Username, email or user ID<input value={permissionUserId} onChange={(event) => setPermissionUserId(event.target.value)} placeholder="e.g. pranav or user@example.com" autoComplete="off" required /></label><label>Role<select value={permissionRole} onChange={(event) => setPermissionRole(event.target.value as PermissionItem['role'])}><option value="viewer">Viewer</option><option value="commenter">Commenter</option><option value="editor">Editor</option><option value="owner">Owner</option></select></label><button className="button button-primary" disabled={actionBusy}><Plus size={16} /> Grant access</button></form><div className="permission-list"><h3>People with access</h3>{permissions.length === 0 ? <p className="muted-copy">No additional access has been granted.</p> : permissions.map((permission) => <div className="permission-person" key={permission.id}><span className="permission-avatar"><CircleUserRound size={17} /></span><span className="permission-user">{permission.user_id}</span><span className={`role-chip ${permission.role}`}>{permission.role}</span><button className="icon-button" title="Remove access" aria-label="Remove access" onClick={() => void revokePermission(permission.id)}><X size={15} /></button></div>)}</div></section></div>}
    </div>
  )
}

export default App
