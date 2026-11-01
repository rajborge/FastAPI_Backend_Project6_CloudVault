import type { FileItem, SharedResource } from './api'

export const roleDescriptions: Record<string, string> = {
  viewer: 'Preview and download clean files.',
  commenter: 'Preview, download, and add comments.',
  editor: 'Comment, rename, move, and move files to Trash. Folder editors can create subfolders.',
  owner: 'Full control, including sharing, version replacement, and permanent deletion.',
}

export function sharedFile(item: SharedResource): FileItem {
  return { id: item.resource_id, original_name: item.name, mime_type: item.mime_type ?? 'application/octet-stream',
    size: item.size ?? 0, folder_id: item.parent_id, created_at: item.created_at, scan_status: item.scan_status ?? 'PENDING_SCAN',
    effective_role: item.effective_role, capabilities: item.capabilities, owner_username: item.owner_username }
}
