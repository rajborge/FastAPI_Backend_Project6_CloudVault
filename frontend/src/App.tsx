import { AccessManager, SharingPanel } from './SharingPanel'
import { sharedFile } from './sharing'
import { FileTools, FolderPicker, ShareManager, SecuritySettings } from './WorkspaceTools'
import { authenticatedFetch } from './api'
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
  type SharedResource,
  type AuditLogItem,
  type SearchResult,
} from './api'
import './App.css'

type View = 'files' | 'shared' | 'activity' | 'trash'
type Transfer = { id: string; fileId?: string; name: string; progress: number; status: 'uploading' | 'scanning' | 'done' | 'error'; message?: string }

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
  const [mfaCode, setMfaCode] = useState('')
  const [toolFile, setToolFile] = useState<FileItem | null>(null)
  const [moving, setMoving] = useState<{ type: 'file' | 'folder'; id: string } | null>(null)
  const [shareManager, setShareManager] = useState(false)
  const [securitySettings, setSecuritySettings] = useState(false)
  const [quota, setQuota] = useState<{ used: number; reserved: number; limit: number } | null>(null)
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
  const [actionBusy, setActionBusy] = useState(false)
  const uploadControllers = useRef(new Map<string, AbortController>())
  const fileInput = useRef<HTMLInputElement>(null)

  const currentFolder = folderStack.at(-1) ?? null
  const currentFolderId = currentFolder?.id ?? null
  const notificationCursor = useRef(0)
  const normalizedSearch = search.trim()
  const intelligentSearchActive = view === 'files' && normalizedSearch.length >= 2
  const visibleFiles = contents.files
  const visibleFolders = contents.folders
  const visibleTrash = trash.filter((file) => file.original_name.toLowerCase().includes(search.toLowerCase()))
  const visibleShared = sharedResources.filter((resource) => `${resource.name} ${resource.owner_username} ${resource.owner_email} ${resource.recipient_username} ${resource.recipient_email}`.toLowerCase().includes(search.toLowerCase()))
  const visibleAudit = auditLogs.filter((entry) => `${entry.action} ${entry.details}`.toLowerCase().includes(search.toLowerCase()))

  const handleSessionExpired = useCallback(() => {
    for (const controller of uploadControllers.current.values()) controller.abort()
    uploadControllers.current.clear()
    for (const key of Object.keys(sessionStorage)) {
      if (key.startsWith('cloudvault.upload:')) sessionStorage.removeItem(key)
    }
    setToolFile(null); setMoving(null); setShareManager(false); setSecuritySettings(false)
    setShareFile(null); setPermissionFile(null); setPermissionFolder(null); setFolderDialog(false)
    setSharedResources([]); setAuditLogs([]); setTrash([]);
    setSearch(''); setSearchResults([]); setTransfers([]); setQuota(null); setMessage(''); setError('')
    clearSession()
    sessionStorage.removeItem('cloudvault.identity')
    setToken(null)
    setIdentity('')
    setFolderStack([])
    setContents(emptyContents)
  }, [])

  const reload = useCallback(async (showSpinner = true) => {
    if (!token) return
    if (showSpinner) {
      setLoading(true)
      setError('')
    }
    try {
      setQuota(await apiRequest(`/users/me/storage`))
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
        const folderContents = await loadFolderContents(currentFolderId)
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
  }, [token, view, currentFolderId, handleSessionExpired])

  useEffect(() => {
    if (token) startTransition(() => { void reload(false) })
  }, [token, view, currentFolder?.id, reload])


  useEffect(() => {
    if (!token || view !== 'files') {
      startTransition(() => { setSearchResults([]); setSearchBusy(false) })
      return
    }

    const query = search.trim()
    if (query.length < 2) {
      startTransition(() => { setSearchResults([]); setSearchBusy(false) })
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
    const files = new Map(contents.files.map((file) => [file.id, file]))
    startTransition(() => setTransfers((items) => items.map((item) => {
      const file = item.fileId ? files.get(item.fileId) : undefined
      if (item.status !== 'scanning' || !file) return item
      if (file.scan_status === 'CLEAN') return { ...item, status: 'done', message: 'Ready' }
      if (file.scan_status === 'INFECTED') return { ...item, status: 'error', message: 'Blocked by malware scan' }
      return item
    })))
  }, [contents.files])

  useEffect(() => {
    if (!folderDialog && !shareFile && !permissionFile && !permissionFolder) return
    const previous = document.activeElement as HTMLElement | null
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]')
    const focusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>('button, input, select, textarea, a[href], [tabindex="0"]') ?? []).filter((el) => !el.hasAttribute('disabled'))
    focusable()[0]?.focus()
    const handle = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setFolderDialog(false); setShareFile(null); setPermissionFile(null); setPermissionFolder(null) }
      if (event.key !== 'Tab') return
      const items = focusable(), first = items[0], last = items.at(-1)
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
    document.addEventListener('keydown', handle)
    return () => { document.removeEventListener('keydown', handle); previous?.focus() }
  }, [folderDialog, shareFile, permissionFile, permissionFolder])

  useEffect(() => {
    if (!token) return
    const controller = new AbortController()
    let cursor = notificationCursor.current
    async function connect() {
      while (!controller.signal.aborted) {
        try {
          const response = await authenticatedFetch(`/notifications/stream?after=${cursor}`, { signal: controller.signal })
          const reader = response.body?.getReader()
          if (!reader) return
          const decoder = new TextDecoder()
          let buffer = ''
          while (!controller.signal.aborted) {
            const chunk = await reader.read()
            if (chunk.done) break
            buffer += decoder.decode(chunk.value, { stream: true })
            let boundary: number
            while ((boundary = buffer.indexOf('\n\n')) >= 0) {
              const event = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2)
              const data = event.split('\n').find((line) => line.startsWith('data: '))
              if (data) {
                const notification = JSON.parse(data.slice(6)) as { sequence: number; message: string }
                cursor = notification.sequence
                notificationCursor.current = cursor
                setMessage(notification.message)
                void reload(false)
              }
            }
          }
        } catch (cause) { if (controller.signal.aborted) return; if (cause instanceof ApiError && cause.status === 401) { handleSessionExpired(); return } }
        await new Promise<void>((resolve) => { const timer = window.setTimeout(resolve, 3000); controller.signal.addEventListener('abort', () => { clearTimeout(timer); resolve() }, { once: true }) })
      }
    }
    void connect()
    return () => controller.abort()
  }, [token, reload, handleSessionExpired])

  function notify(text: string) {
    setMessage(text)
    window.setTimeout(() => setMessage(''), 3200)
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
        await signIn(email || username, password, mfaCode)
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
      const controller = new AbortController()
      uploadControllers.current.set(id, controller)
      try {
        const uploaded = await uploadFile(file, currentFolder?.id ?? null, (progress) => {
          setTransfers((items) => items.map((item) => item.id === id ? { ...item, progress } : item))
        }, controller.signal)
        setTransfers((items) => items.map((item) => item.id === id ? { ...item, fileId: uploaded.id, progress: 100, status: 'scanning' } : item))
      } catch (cause) {
        setTransfers((items) => items.map((item) => item.id === id ? {
          ...item,
          status: 'error',
          message: controller.signal.aborted ? 'Cancelled' : cause instanceof Error ? `${cause.message} Select the same file to resume.` : 'Upload failed',
        } : item))
      } finally { uploadControllers.current.delete(id) }
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

  function handleMoveFolder(folder: FolderItem) { setMoving({ type: 'folder', id: folder.id }) }

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

  function handleMoveFile(file: FileItem) { setMoving({ type: 'file', id: file.id }) }

  async function renameFile(file: FileItem) {
    const name = window.prompt('New file name', file.original_name)?.trim()
    if (!name || name === file.original_name) return
    try { await apiRequest(`/files/${file.id}/rename`, { method: 'PATCH', body: JSON.stringify({ name }) }); await reload() }
    catch (cause) { setError((cause as Error).message) }
  }

  function openSharedResource(resource: SharedResource) {
    if (resource.resource_type === 'folder') {
      setSearch('')
      setView('files')
      setFolderStack([{ id: resource.resource_id, name: resource.name, parent_id: resource.parent_id, created_at: resource.created_at, owner_username: resource.owner_username, effective_role: resource.effective_role, capabilities: resource.capabilities }])
      return
    }
    setToolFile(sharedFile(resource))
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

  function openPermissionManager(file: FileItem) { setPermissionFolder(null); setPermissionFile(file) }
  function openFolderPermissionManager(folder: FolderItem) { setPermissionFile(null); setPermissionFolder(folder) }

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
            {authMode === 'login' && <label>Authenticator code <span className="optional-label">If MFA is enabled</span><input inputMode="numeric" autoComplete="one-time-code" value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} maxLength={64} /></label>}
            <a href="/?account_action=forgot">Forgot password?</a>
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
        <button className="button button-primary sidebar-upload" disabled={currentFolder?.capabilities?.can_add_files === false} title={currentFolder?.capabilities?.can_add_files === false ? 'Only the owner can upload into this shared folder' : 'Upload files'} onClick={() => fileInput.current?.click()}><Upload size={17} /> Upload files</button>
        <input ref={fileInput} className="visually-hidden" type="file" multiple onChange={handleFilesSelected} />
        <nav className="side-nav" aria-label="Main navigation">
          <p className="nav-label">WORKSPACE</p>
          <button className={`nav-item ${view === 'files' ? 'selected' : ''}`} onClick={() => { setView('files'); setFolderStack([]) }}><Home size={17} /><span>My files</span><span className="nav-count">{contents.files.length}</span></button>
          <button className={`nav-item ${view === 'shared' ? 'selected' : ''}`} onClick={() => { setView('shared'); setFolderStack([]) }}><UsersRound size={17} /><span>Shared with me</span></button>
          <button className={`nav-item ${view === 'activity' ? 'selected' : ''}`} onClick={() => { setView('activity'); setFolderStack([]) }}><Clock3 size={17} /><span>Activity</span></button>
          <button className={`nav-item ${view === 'trash' ? 'selected' : ''}`} onClick={() => { setView('trash'); setFolderStack([]) }}><Trash2 size={17} /><span>Trash</span></button>
        </nav>
        <button className="nav-item" onClick={() => setShareManager(true)}>Sharing links</button>
        <button className="nav-item" onClick={() => setSecuritySettings(true)}>Account security</button>
        <div className="sidebar-spacer" />
        {quota && <div className="quota-summary"><label htmlFor="quota-meter">Storage: {formatBytes(quota.used)} / {formatBytes(quota.limit)}</label><meter id="quota-meter" min={0} max={quota.limit} value={quota.used + quota.reserved} />{quota.reserved > 0 && <small>{formatBytes(quota.reserved)} reserved for uploads</small>}</div>}
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
            {view === 'files' && <div className="heading-actions"><button className="button button-secondary" disabled={currentFolder?.capabilities?.can_edit === false} onClick={() => setFolderDialog(true)}><Plus size={17} /> New folder</button><button className="button button-primary heading-upload" disabled={currentFolder?.capabilities?.can_add_files === false} title={currentFolder?.capabilities?.can_add_files === false ? 'Only the owner can upload into this shared folder' : 'Upload files'} onClick={() => fileInput.current?.click()}><Upload size={17} /> Upload</button></div>}
          </div>

          {view === 'files' && currentFolder?.owner_username && <p className="shared-folder-context">Owner: {currentFolder.owner_username} · Your role: {currentFolder.effective_role ?? 'owner'}</p>}
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
                            <button className="file-open-name" title="Open preview" onClick={() => setToolFile(file)}>{file.original_name}</button>
                            <span className={`match-chip ${file.score >= 0.999 ? 'exact' : ''}`}>{file.score >= 0.999 ? 'Exact match' : 'Content match'}</span>
                          </div>
                          {file.snippet && <p className="search-result-snippet">{cleanSearchSnippet(file.snippet)}</p>}
                          <div className="search-result-meta"><span>{file.mime_type}</span><span>·</span><span>{formatBytes(file.size)}</span><span>·</span><span>{formatDate(file.created_at)}</span><span>·</span><span>{file.scan_status === 'CLEAN' ? (file.index_status === 'FAILED' ? 'Index failed' : file.index_status === 'INDEXING' ? 'Indexing' : 'Ready') : file.scan_status}</span><span>{file.index_status === 'FAILED' ? 'Search indexing failed' : file.index_status === 'INDEXING' ? 'Indexing…' : ''}</span></div>
                        </div>
                        <div className="search-result-actions">
                          <button className="icon-button row-action" title="Download" aria-label={`Download ${file.original_name}`} disabled={file.scan_status !== 'CLEAN'} onClick={() => void handleDownload(file)}><Download size={16} /></button>
                          <button className="icon-button row-action" title="Share" aria-label={`Share ${file.original_name}`} disabled={file.capabilities?.can_manage_access === false} onClick={() => { setShareFile(file); setShareExpiry('7_days') }}><Share2 size={16} /></button>
                          <details className="action-menu"><summary role="button" className="icon-button row-action" aria-label={`More actions for ${file.original_name}`}><MoreHorizontal size={17} /></summary><div className="menu-popover"><button onClick={() => setToolFile(file)}>Open preview</button><button disabled={file.capabilities?.can_edit === false} onClick={() => void renameFile(file)}>Rename</button><button disabled={file.capabilities?.can_manage_access === false} onClick={() => void openPermissionManager(file)}><UsersRound size={15} /> Manage access</button><button disabled={file.capabilities?.can_edit === false} onClick={() => void handleMoveFile(file)}><FolderClosed size={15} /> Move</button><button className="danger-item" disabled={file.capabilities?.can_trash === false} onClick={() => void handleTrash(file)}><Trash2 size={15} /> Move to trash</button></div></details>
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
                  <div className="empty-state"><div className="empty-art"><FolderClosed size={28} /></div><h2>A little room to begin</h2><p>Create a folder or upload a file to get your workspace started.</p><div className="empty-actions"><button className="button button-secondary" disabled={currentFolder?.capabilities?.can_edit === false} onClick={() => setFolderDialog(true)}><Plus size={16} /> New folder</button><button className="button button-primary" disabled={currentFolder?.capabilities?.can_add_files === false} title={currentFolder?.capabilities?.can_add_files === false ? 'Only the owner can upload into this shared folder' : 'Upload files'} onClick={() => fileInput.current?.click()}><Upload size={16} /> Upload a file</button></div></div>
                ) : (
                  <div className="file-list">
                    {visibleFolders.map((folder) => <div className="file-row folder-row" key={folder.id} role="button" tabIndex={0} onClick={() => setFolderStack((stack) => [...stack, folder])} onKeyDown={(event) => { if (event.key === 'Enter') setFolderStack((stack) => [...stack, folder]) }}>
                      <div className="file-name-cell"><span className="file-type folder-type"><FolderClosed size={18} /></span><span className="file-title">{folder.name}</span></div><span className="file-date">{formatDate(folder.created_at)}</span><span className="file-size">—</span><span className="file-status"><span className="status-text">Folder</span><ChevronRight className="folder-arrow" size={16} /></span><span className="file-actions" onClick={(event) => event.stopPropagation()}><details className="action-menu"><summary role="button" className="icon-button row-action" aria-label={`More actions for ${folder.name}`}><MoreHorizontal size={17} /></summary><div className="menu-popover"><button disabled={folder.capabilities?.can_edit === false} onClick={() => void handleRenameFolder(folder)}><Pencil size={15} /> Rename</button><button disabled={folder.capabilities?.can_edit === false} onClick={() => void handleMoveFolder(folder)}><FolderClosed size={15} /> Move</button><button disabled={folder.capabilities?.can_manage_access === false} onClick={() => void openFolderPermissionManager(folder)}><UsersRound size={15} /> Manage access</button><button className="danger-item" disabled={folder.capabilities?.can_delete_folder === false} onClick={() => void handleDeleteFolder(folder)}><Trash2 size={15} /> Delete folder</button></div></details></span>
                    </div>)}
                    {visibleFiles.map((file) => <div className="file-row" key={file.id}>
                      <div className="file-name-cell"><span className="file-type">{fileIcon(file)}</span><button className="file-title file-open-name" title="Open preview" onClick={() => setToolFile(file)}>{file.original_name}</button></div>
                      <span className="file-date">{formatDate(file.created_at)}</span><span className="file-size">{formatBytes(file.size)}</span>
                      <span className="file-status"><span className={`status-dot ${file.scan_status.toLowerCase()}`} />{file.scan_status === 'PENDING_SCAN' ? 'Queued' : file.scan_status === 'SCANNING' ? 'Scanning' : file.scan_status === 'CLEAN' ? (file.index_status === 'FAILED' ? 'Index failed' : file.index_status === 'INDEXING' ? 'Indexing' : 'Ready') : file.scan_status}</span>
                      <span className="file-actions">
                        <button className="icon-button row-action" title="Download" aria-label={`Download ${file.original_name}`} disabled={file.scan_status !== 'CLEAN'} onClick={() => void handleDownload(file)}><Download size={16} /></button>
                        <details className="action-menu"><summary role="button" className="icon-button row-action" aria-label={`More actions for ${file.original_name}`}><MoreHorizontal size={17} /></summary><div className="menu-popover"><button disabled={file.capabilities?.can_manage_access === false} onClick={() => { setShareFile(file); setShareExpiry('7_days') }}><Share2 size={15} /> Create share link</button><button onClick={() => setToolFile(file)}>Open preview</button><button disabled={file.capabilities?.can_manage_access === false} onClick={() => void openPermissionManager(file)}><UsersRound size={15} /> Manage access</button><button disabled={file.capabilities?.can_edit === false} onClick={() => { const nextName = window.prompt('New file name', file.original_name); if (nextName?.trim()) void apiRequest(`/files/${file.id}/rename`, { method: 'PATCH', body: JSON.stringify({ name: nextName.trim() }) }).then(() => reload()).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'Rename failed.')) }}><Pencil size={15} /> Rename</button><button disabled={file.capabilities?.can_edit === false} onClick={() => void handleMoveFile(file)}><FolderClosed size={15} /> Move</button><button className="danger-item" disabled={file.capabilities?.can_trash === false} onClick={() => void handleTrash(file)}><Trash2 size={15} /> Move to trash</button></div></details>
                      </span>
                    </div>)}
                  </div>
                )}
              </div>
            )
          ) : view === 'shared' ? (
            <SharingPanel incoming={visibleShared} search={search} loading={loading} onOpen={openSharedResource} onDownload={(file) => void handleDownload(file)} onManage={(item) => { if (item.resource_type === 'file') openPermissionManager(sharedFile(item)); else openFolderPermissionManager({ id: item.resource_id, name: item.name, parent_id: item.parent_id, created_at: item.created_at }) }} onChanged={() => void reload(false)} />
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

      {toolFile && <FileTools file={toolFile} onClose={() => setToolFile(null)} onChange={() => void reload(false)} />}
      {shareManager && <ShareManager onClose={() => setShareManager(false)} />}
      {securitySettings && <SecuritySettings onClose={() => setSecuritySettings(false)} />}
      {moving && <FolderPicker excluded={moving.type === 'folder' ? moving.id : undefined} onClose={() => setMoving(null)} onChoose={async (id) => { if (moving.type === 'file') await moveFile(moving.id, id); else await moveFolder(moving.id, id); await reload(); notify('Moved successfully') }} />}
      {transfers.length > 0 && <aside className="transfer-panel" aria-label="Upload activity"><div className="transfer-heading"><div><span className="transfer-icon"><Upload size={15} /></span><strong>Transfers</strong></div><button className="icon-button" aria-label="Dismiss transfers" onClick={() => setTransfers([])}><X size={16} /></button></div>{transfers.map((transfer) => <div className="transfer-row" key={transfer.id}><div className="transfer-file"><span className="transfer-name">{transfer.name}</span><span>{transfer.status === 'uploading' && <button className="icon-button" aria-label={`Cancel upload ${transfer.name}`} onClick={() => uploadControllers.current.get(transfer.id)?.abort()}>×</button>}</span><span className={`transfer-state ${transfer.status}`}>{transfer.status === 'uploading' ? `${transfer.progress}%` : transfer.status === 'scanning' ? 'Scanning' : transfer.message}</span></div><div className="progress-track"><span style={{ width: `${transfer.progress}%` }} /></div></div>)}</aside>}

      {folderDialog && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setFolderDialog(false) }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="folder-title"><div className="modal-head"><div><p className="eyebrow">ORGANIZE</p><h2 id="folder-title">New folder</h2></div><button className="icon-button" aria-label="Close" onClick={() => setFolderDialog(false)}><X size={18} /></button></div><form onSubmit={handleCreateFolder}><label>Folder name<input autoFocus value={folderName} onChange={(event) => setFolderName(event.target.value)} maxLength={255} required /></label><div className="modal-actions"><button type="button" className="button button-secondary" onClick={() => setFolderDialog(false)}>Cancel</button><button className="button button-primary" disabled={actionBusy}>{actionBusy ? 'Creating…' : 'Create folder'}</button></div></form></section></div>}

      {shareFile && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setShareFile(null) }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="share-title"><div className="modal-head"><div><p className="eyebrow">SECURE SHARING</p><h2 id="share-title">Share file</h2><p className="modal-file-name">{shareFile.original_name}</p></div><button className="icon-button" aria-label="Close" onClick={() => setShareFile(null)}><X size={18} /></button></div><form onSubmit={handleShare}><label>Link expires<select value={shareExpiry} onChange={(event) => setShareExpiry(event.target.value)}><option value="never">Never</option><option value="1_day">After 1 day</option><option value="7_days">After 7 days</option><option value="30_days">After 30 days</option></select></label><label>Password <span className="optional-label">Optional</span><input type="password" autoComplete="new-password" value={sharePassword} onChange={(event) => setSharePassword(event.target.value)} /></label><label>Download limit <span className="optional-label">Optional</span><input type="number" min="1" value={shareLimit} onChange={(event) => setShareLimit(event.target.value)} placeholder="Unlimited" /></label><div className="modal-actions"><button type="button" className="button button-secondary" onClick={() => setShareFile(null)}>Cancel</button><button className="button button-primary" disabled={actionBusy}><Copy size={15} />{actionBusy ? 'Creating…' : 'Create & copy link'}</button></div></form></section></div>}

      {(permissionFile || permissionFolder) && <AccessManager file={permissionFile} folder={permissionFolder} onClose={() => { setPermissionFile(null); setPermissionFolder(null) }} onChange={() => void reload(false)} />}

    </div>
  )
}

export default App
