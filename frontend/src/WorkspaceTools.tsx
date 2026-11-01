import EmailVerification from './EmailVerification'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { apiRequest, authenticatedFetch, loadFolderContents, replaceSession, resolveFileLink, downloadFile, type AccessInfo, type FileItem, type FolderItem } from './api'

export function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const dialog = ref.current
    dialog?.showModal()
    return () => { dialog?.close(); previous?.focus() }
  }, [])
  return <dialog ref={ref} aria-label={title} className="tool-dialog" onCancel={onClose} onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
    <header><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="Close dialog">×</button></header>
    {children}
  </dialog>
}

export function FolderPicker({ onClose, onChoose, excluded }: { onClose: () => void; onChoose: (id: string | null) => Promise<void>; excluded?: string }) {
  const [stack, setStack] = useState<FolderItem[]>([])
  const [folders, setFolders] = useState<FolderItem[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const current = stack.at(-1)?.id ?? null
  useEffect(() => {
    let active = true
    loadFolderContents(current).then((data) => { if (active) setFolders(data.folders) })
      .catch((cause: Error) => { if (active) setError(cause.message) })
    return () => { active = false }
  }, [current])
  return <Dialog title="Choose destination folder" onClose={onClose}>
    <p>{['My files', ...stack.map((f) => f.name)].join(' / ')}</p>
    {stack.length > 0 && <button className="button button-secondary" onClick={() => setStack((s) => s.slice(0, -1))}>Up one level</button>}
    <div className="tool-list">{folders.filter((f) => f.id !== excluded).map((folder) => <button key={folder.id} onClick={() => setStack((s) => [...s, folder])}>📁 {folder.name}</button>)}</div>
    {error && <p role="alert" className="form-error">{error}</p>}
    <button className="button button-primary" disabled={busy || current === excluded} onClick={async () => {
      setBusy(true)
      try { await onChoose(current); onClose() } catch (cause) { setError((cause as Error).message) } finally { setBusy(false) }
    }}>{busy ? 'Moving…' : 'Move here'}</button>
  </Dialog>
}

type Comment = { id: string; body: string; username: string; created_at: string; can_delete?: boolean }
type Version = { id: string; original_name: string; size: number; created_at: string }

export function FileTools({ file, onClose, onChange }: { file: FileItem; onClose: () => void; onChange: () => void }) {
  const [tab, setTab] = useState('preview')
  const [access, setAccess] = useState<AccessInfo | null>(null)
  const [text, setText] = useState<string | null>(null)
  const [comments, setComments] = useState<Comment[]>([])
  const [versions, setVersions] = useState<Version[]>([])
  const [candidates, setCandidates] = useState<FileItem[]>([])
  const [source, setSource] = useState('')
  const [body, setBody] = useState('')
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    apiRequest<AccessInfo>(`/files/${file.id}/access`, { signal: controller.signal }).then(setAccess)
      .catch((cause: Error) => { if (!controller.signal.aborted) setError(cause.message) })
    return () => controller.abort()
  }, [file.id])
  useEffect(() => {
    const controller = new AbortController()
    let previewUrl = ''
    if (tab === 'comments') apiRequest<Comment[]>(`/files/${file.id}/comments`, { signal: controller.signal }).then(setComments).catch(fail)
    if (tab === 'versions') {
      apiRequest<Version[]>(`/files/${file.id}/versions`, { signal: controller.signal }).then(setVersions).catch(fail)
      if (access?.capabilities.can_replace) loadFolderContents(file.folder_id).then((data) => setCandidates(data.files.filter((f) => f.id !== file.id && f.scan_status === 'CLEAN'))).catch(fail)
    }
    if (tab === 'preview') resolveFileLink(file.id, true, controller.signal).then(async (link) => {
      if (controller.signal.aborted) return
      if (file.mime_type === 'text/plain') {
        const response = link.external ? await fetch(link.url, { signal: controller.signal, credentials: 'omit', referrerPolicy: 'no-referrer' }) : await authenticatedFetch(link.url, { signal: controller.signal })
        if (!response.ok) throw new Error('The text preview is unavailable. Download the file to open it.')
        const value = await response.text()
        if (!controller.signal.aborted) setText(value)
      } else if (link.external) setUrl(link.url)
      else {
        const response = await authenticatedFetch(link.url, { signal: controller.signal })
        const blob = await response.blob()
        if (controller.signal.aborted) return
        previewUrl = URL.createObjectURL(blob); setUrl(previewUrl)
      }
    }).catch(fail)
    function fail(cause: Error) { if (!controller.signal.aborted) setError(cause.message) }
    return () => { controller.abort(); if (previewUrl) URL.revokeObjectURL(previewUrl) }
  }, [file.id, file.folder_id, file.mime_type, tab, revision, access?.capabilities.can_replace])
  async function action(work: () => Promise<unknown>) {
    setBusy(true); setError('')
    try { await work(); setRevision((n) => n + 1); onChange() } catch (cause) { setError((cause as Error).message) } finally { setBusy(false) }
  }
  return <Dialog title={file.original_name} onClose={onClose}>
    {access && <p className="muted-copy">Owner: {access.owner_username} · Your role: {access.effective_role}</p>}
    <button className="button button-secondary" disabled={file.scan_status !== 'CLEAN'} onClick={() => void downloadFile(file).catch((cause: Error) => setError(cause.message))}>Download file</button>
    <nav className="tool-tabs" aria-label="File tools">{['preview', 'comments', 'versions'].map((name) => <button className={tab === name ? 'active' : ''} key={name} onClick={() => { setTab(name); setError(''); setUrl(''); setText(null) }}>{name}</button>)}</nav>
    {error && <p role="alert" className="form-error">{error}</p>}
    {file.index_status === 'FAILED' && <p role="status">Search indexing failed. <button disabled={busy} onClick={() => void action(() => apiRequest(`/search/index/${file.id}`, { method: 'POST' }))}>Retry indexing</button></p>}
    {tab === 'preview' && (file.mime_type === 'text/plain' && text !== null ? <pre className="text-preview">{text}</pre> : url ? file.mime_type.startsWith('image/') ? <img className="file-preview" src={url} alt={file.original_name} referrerPolicy="no-referrer" /> : <iframe className="file-preview" title={`Preview of ${file.original_name}`} src={url} referrerPolicy="no-referrer" /> : !error && <p>Preparing preview…</p>)}
    {tab === 'comments' && <><div className="tool-list">{comments.map((comment) => <article key={comment.id}><strong>{comment.username}</strong><p>{comment.body}</p>{comment.can_delete && <button onClick={() => void action(() => apiRequest(`/files/${file.id}/comments/${comment.id}`, { method: 'DELETE' }))}>Delete comment</button>}</article>)}{comments.length === 0 && <p>No comments yet.</p>}</div>
      {access?.capabilities.can_comment ? <form onSubmit={(e) => { e.preventDefault(); void action(async () => { await apiRequest(`/files/${file.id}/comments`, { method: 'POST', body: JSON.stringify({ body }) }); setBody('') }) }}><label>Add a comment<textarea value={body} onChange={(e) => setBody(e.target.value)} required maxLength={5000} /></label><button className="button button-primary" disabled={busy}>Post comment</button></form> : <p className="muted-copy">Your role allows reading comments. Ask the owner for Commenter or Editor access to post.</p>}</>}
    {tab === 'versions' && <><p>Upload the replacement into this folder first and wait for it to finish scanning. Past revisions count towards your storage quota.</p>{access?.capabilities.can_replace && <form onSubmit={(e) => { e.preventDefault(); void action(() => apiRequest(`/files/${file.id}/versions`, { method: 'POST', body: JSON.stringify({ source_file_id: source }) })) }}><label>Use uploaded file as the latest version<select required value={source} onChange={(e) => setSource(e.target.value)}><option value="">Choose a clean file</option>{candidates.map((f) => <option key={f.id} value={f.id}>{f.original_name}</option>)}</select></label><button className="button button-primary" disabled={!source || busy}>Save new version</button></form>}<div className="tool-list">{versions.map((version) => <article key={version.id}><p>{version.original_name} · {new Date(version.created_at).toLocaleString()} · {version.size} bytes</p>{access?.capabilities.can_replace && <button disabled={busy} onClick={() => void action(() => apiRequest(`/files/${file.id}/versions/${version.id}/restore`, { method: 'POST' }))}>Restore this version</button>}</article>)}{versions.length === 0 && <p>No previous versions.</p>}</div></>}
  </Dialog>
}

type Share = { id: string; name: string; is_active: boolean; share_url: string; download_count: number; max_downloads: number | null }
export function ShareManager({ onClose }: { onClose: () => void }) {
  const [shares, setShares] = useState<Share[]>([])
  const [error, setError] = useState('')
  useEffect(() => { apiRequest<Share[]>('/shares').then(setShares).catch((e: Error) => setError(e.message)) }, [])
  return <Dialog title="Your sharing links" onClose={onClose}>{error && <p role="alert">{error}</p>}<div className="tool-list">{shares.map((s) => <article key={s.id}><strong>{s.name}</strong><p>{s.is_active ? 'Active' : 'Inactive'} · {s.download_count} downloads{s.max_downloads ? ` / ${s.max_downloads}` : ''}</p><button onClick={() => void navigator.clipboard.writeText(s.share_url).catch(() => setError('Copy failed.'))}>Copy link</button><button disabled={!s.is_active} onClick={async () => { try { await apiRequest(`/shares/${s.id}`, { method: 'DELETE' }); setShares((rows) => rows.map((row) => row.id === s.id ? { ...row, is_active: false } : row)) } catch (e) { setError((e as Error).message) } }}>Revoke</button></article>)}</div>{shares.length === 0 && <p>No sharing links yet.</p>}</Dialog>
}

export function SecuritySettings({ onClose }: { onClose: () => void }) {
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [secret, setSecret] = useState('')
  const [message, setMessage] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [busy, setBusy] = useState(false)
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])
  useEffect(() => { apiRequest<{ mfa_enabled: boolean }>('/users/me/storage').then((d) => setEnabled(d.mfa_enabled)).catch((e: Error) => setMessage(e.message)) }, [])
  async function submit(path: string) {
    setBusy(true); setMessage('')
    try {
      const result = await apiRequest<{ secret?: string; recovery_codes?: string[]; access_token: string; csrf_token: string; token_type: string }>(`/auth/mfa/${path}`, { method: 'POST', body: JSON.stringify({ password, code: code || null }) })
      if (result?.access_token) replaceSession(result)
      if (path === 'setup') { setSecret(result.secret ?? ''); setMessage('Add this key to your authenticator, then enter its code to enable MFA.') }
      else { setSecret(''); setEnabled(path === 'enable'); setPassword(''); setCode(''); setRecoveryCodes(result?.recovery_codes ?? []); setMessage('Security settings updated.') }
    } catch (e) { setMessage((e as Error).message) } finally { setBusy(false) }
  }
  return <Dialog title="Account security" onClose={onClose}>
    <p className="muted-copy">Manage your email and add an extra layer of protection.</p><EmailVerification />
    <section className="security-section" aria-label="Authenticator setup">
      <div className="security-section-heading"><h3>Two-step authentication</h3><span className="role-chip">{enabled ? 'Enabled' : 'Not enabled'}</span></div>
      <p className="muted-copy">Use an authenticator app for your sign-in codes. Email verification and authenticator codes are separate; you can set up MFA before verifying your email.</p>
      {!enabled && <ol className="mfa-steps"><li>Enter your CloudVault password and choose Set up MFA.</li><li>In Google Authenticator, Microsoft Authenticator, or another TOTP app, add an account using a setup key. Choose a time-based key and paste the key shown below.</li><li>Enter the app’s current 6-digit code here and choose Enable MFA.</li></ol>}
      <label>Current password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
      {secret && <div className="mfa-key"><small>Private authenticator setup key</small><code>{secret}</code><p>Keep this key private. The code comes from your authenticator app and changes every 30 seconds.</p></div>}
      {(secret || enabled) && <label>{enabled ? 'Authenticator or recovery code' : '6-digit authenticator code'}<input inputMode={enabled ? 'text' : 'numeric'} autoComplete="one-time-code" value={code} maxLength={64} onChange={(e) => setCode(e.target.value.replace(/\s/g, ''))} placeholder={enabled ? 'Current code or a saved recovery code' : '000000'} /></label>}
      {message && <p role="status">{message}</p>}
      <div className="sharing-actions">{!enabled && !secret && <button className="button button-primary" disabled={!password || busy} onClick={() => void submit('setup')}>{busy ? 'Setting up…' : 'Set up MFA'}</button>}{secret && <button className="button button-primary" disabled={!password || !/^\d{6}$/.test(code) || busy} onClick={() => void submit('enable')}>{busy ? 'Enabling…' : 'Enable MFA'}</button>}{enabled && <button className="button button-secondary" disabled={!password || code.length < 6 || busy} onClick={() => void submit('disable')}>Disable MFA</button>}</div>
      {recoveryCodes.length > 0 && <div className="recovery-codes"><h4>Save your recovery codes now</h4><p>These codes are shown once. Store them somewhere private. Each code can be used once if you lose access to your authenticator.</p><pre>{recoveryCodes.join('\n')}</pre></div>}
    </section><p className="security-footer"><a href="/?account_action=forgot">Reset your password</a></p>
  </Dialog>
}
