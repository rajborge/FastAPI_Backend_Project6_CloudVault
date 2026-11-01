import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest, getResourcePermissions, grantResourcePermission, type AccessInfo, type FileItem, type FolderItem, type PermissionItem, type SharedResource } from './api'
import { Dialog } from './WorkspaceTools'
import { File, Folder } from 'lucide-react'

import { roleDescriptions, sharedFile } from './sharing'

export function SharingPanel({ incoming, search, loading, onOpen, onDownload, onManage, onChanged }: {
  incoming: SharedResource[]; search: string; loading: boolean;
  onOpen: (item: SharedResource) => void; onDownload: (file: FileItem) => void;
  onManage: (item: SharedResource) => void; onChanged: () => void;
}) {
  const [tab, setTab] = useState<'received' | 'sent'>('received')
  const [outgoing, setOutgoing] = useState<SharedResource[]>([])
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    if (tab !== 'sent') return
    const controller = new AbortController()
    apiRequest<SharedResource[]>('/permissions/shared-by-me', { signal: controller.signal }).then(setOutgoing)
      .catch((cause: Error) => { if (!controller.signal.aborted) setError(cause.message) })
    return () => controller.abort()
  }, [tab, refresh])
  const rows = (tab === 'sent' ? outgoing : incoming).filter((row) =>
    `${row.name} ${row.owner_username} ${row.owner_email} ${row.recipient_username} ${row.recipient_email}`.toLowerCase().includes(search.toLowerCase()))
  return <div className="sharing-panel">
    <div className="sharing-tabs" role="tablist" aria-label="Sharing direction">
      <button role="tab" aria-selected={tab === 'received'} onClick={() => setTab('received')}>Shared with me</button>
      <button role="tab" aria-selected={tab === 'sent'} onClick={() => { setTab('sent'); setRefresh((n) => n + 1) }}>Shared by me</button>
    </div>
    <p className="muted-copy">Account sharing gives access to a signed-in recipient. Public links are managed separately under Sharing links.</p>
    <details className="role-guide"><summary>What can each role do?</summary>{Object.entries(roleDescriptions).map(([role, description]) => <p key={role}><strong>{role[0].toUpperCase() + role.slice(1)}:</strong> {description}</p>)}</details>
    {error && <p role="alert" className="form-error">{error}</p>}
    {loading && tab === 'received' ? <p>Loading shared items…</p> : rows.length === 0 ? <div className="empty-state"><h2>{tab === 'sent' ? 'You have not shared any items yet' : 'Nothing shared with you yet'}</h2><p>Use Manage access on a file or folder to grant another account access.</p></div> :
      <div className="sharing-cards">{rows.map((item) => <article className="sharing-card" key={item.permission_id}>
        <div className="sharing-card-heading"><span className="shared-file-icon">{item.resource_type === 'folder' ? <Folder size={19} /> : <File size={19} />}</span><button className="file-open-name" onClick={() => onOpen(item)}>{item.name}</button><span className={`role-chip ${item.role}`}>{item.role}</span></div>
        <dl><div><dt>Owner / sender</dt><dd>{item.owner_username}<small>{item.owner_email}</small></dd></div><div><dt>Recipient</dt><dd>{tab === 'received' ? 'You' : item.recipient_username}<small>{item.recipient_email}</small></dd></div><div><dt>Shared on</dt><dd>{new Date(item.shared_at).toLocaleString()}</dd></div></dl>
        <p className="sharing-role-description">{roleDescriptions[item.role]}</p>
        {item.resource_type === 'file' && <p className={`scan-label ${item.scan_status === 'CLEAN' ? 'ready' : ''}`}>{item.scan_status === 'CLEAN' ? 'Ready to preview and download' : item.scan_status === 'INFECTED' ? 'Blocked by malware scanning' : 'Scanning in progress — downloads will unlock when clean'}</p>}
        <div className="sharing-actions">
          <button className="button button-secondary" onClick={() => onOpen(item)} disabled={item.resource_type === 'file' && !item.capabilities?.can_preview}>{item.resource_type === 'folder' ? 'Open folder' : 'Open preview'}</button>
          {item.resource_type === 'file' && <button className="button button-primary" disabled={!item.capabilities?.can_download} onClick={() => onDownload(sharedFile(item))}>Download</button>}
          {tab === 'sent' && <><button className="button button-secondary" onClick={() => onManage(item)}>Manage access</button><button className="button button-secondary" onClick={async () => { try { await apiRequest(`/permissions/${item.permission_id}`, { method: 'DELETE' }); setRefresh((n) => n + 1); onChanged() } catch (cause) { setError((cause as Error).message) } }}>Revoke access</button></>}
        </div>
      </article>)}</div>}
  </div>
}

export function AccessManager({ file, folder, onClose, onChange }: { file: FileItem | null; folder: FolderItem | null; onClose: () => void; onChange: () => void }) {
  const resource = folder ?? file!
  const type = folder ? 'folder' : 'file'
  const [access, setAccess] = useState<AccessInfo | null>(null)
  const [people, setPeople] = useState<PermissionItem[]>([])
  const [target, setTarget] = useState('')
  const [role, setRole] = useState<PermissionItem['role']>('viewer')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    apiRequest<AccessInfo>(`/permissions/access?resource_type=${type}&resource_id=${resource.id}`, { signal: controller.signal })
      .then(async (info) => { if (controller.signal.aborted) return; setAccess(info); if (info.capabilities.can_manage_access) setPeople(await getResourcePermissions(type, resource.id)) })
      .catch((cause: Error) => { if (!controller.signal.aborted) setError(cause.message) })
    return () => controller.abort()
  }, [type, resource.id, refresh])
  async function update(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try { await grantResourcePermission(type, resource.id, target, role); setTarget(''); setRefresh((n) => n + 1); onChange() }
    catch (cause) { setError((cause as Error).message) } finally { setBusy(false) }
  }
  return <Dialog title="Manage access" onClose={onClose}>
    <p className="modal-file-name">{'name' in resource ? resource.name : resource.original_name}</p>
    {access && <div className="access-owner"><strong>Owner: {access.owner_username}</strong><small>{access.owner_email}</small><p>Your role: {access.effective_role} — {roleDescriptions[access.effective_role]}</p></div>}
    {error && <p role="alert" className="form-error">{error}</p>}
    {access?.capabilities.can_manage_access ? <>
      <form className="grant-form" onSubmit={update}><label>Username or email<input placeholder="e.g. pranav or user@example.com" value={target} onChange={(e) => setTarget(e.target.value)} required /></label><label>Role<select value={role} onChange={(e) => setRole(e.target.value as PermissionItem['role'])}><option value="viewer">Viewer</option><option value="commenter">Commenter</option><option value="editor">Editor</option></select></label><p className="muted-copy">{roleDescriptions[role]}</p><button className="button button-primary" disabled={busy}>Grant / update access</button></form>
      <div className="permission-list"><h3>People with access</h3>{people.length === 0 && <p>No additional access has been granted.</p>}{people.map((person) => <div className="permission-person" key={person.id}><div className="sharing-person"><strong>{person.username ?? 'User'}</strong><small>{person.email ?? person.user_id}</small></div><span className={`role-chip ${person.role}`}>{person.role}</span><button className="button button-secondary" onClick={() => { setTarget(person.email ?? person.username ?? person.user_id); setRole(person.role === 'owner' ? 'editor' : person.role) }}>Change role</button><button className="icon-button" aria-label={`Remove access for ${person.username ?? person.user_id}`} onClick={async () => { try { await apiRequest(`/permissions/${person.id}`, { method: 'DELETE' }); setRefresh((n) => n + 1); onChange() } catch (cause) { setError((cause as Error).message) } }}>×</button></div>)}</div>
    </> : access && <p>Only the owner can change who has access. Contact {access.owner_username} to request a different role.</p>}
  </Dialog>
}
