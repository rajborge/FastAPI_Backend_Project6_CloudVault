import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update, text
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_stream_user
from app.core.enum import PermissionRole, ResourceType
from app.db.database import SessionLocal, get_db
from app.db.models.collaboration import Comment, Notification
from app.db.models.file import File
from app.db.models.permission import Permission
from app.db.models.sharedFile import SharedFile
from app.db.models.user import User
from app.repositories.file_repository import FileRepository
from app.services.PermissionService import PermissionService
from app.services.file_service import FileService
from app.services.r2_storage_service import R2StorageService
from app.tasks.file_task import enqueue_file_index

router = APIRouter(tags=["Collaboration"])


class CommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class VersionRequest(BaseModel):
    source_file_id: UUID


def require_file(db, user, file_id, role=PermissionRole.VIEWER):
    PermissionService(db).check_permissions(
        user=user,
        resource_type=ResourceType.FILE,
        resource_id=file_id,
        required_role=role,
    )
    file = db.get(File, file_id)
    if file is None or file.is_deleted or file.version_of is not None:
        raise HTTPException(404, "File not found.")
    return file


@router.get("/files/{file_id}/comments")
def list_comments(
    file_id: UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file = require_file(db, current, file_id)
    rows = db.execute(
        select(Comment, User.username)
        .join(User, User.id == Comment.user_id)
        .where(Comment.file_id == file_id)
        .order_by(Comment.created_at)
        .limit(500)
    ).all()
    return [
        {
            "id": c.id,
            "body": c.body,
            "username": name,
            "user_id": c.user_id,
            "created_at": c.created_at,
            "can_delete": c.user_id == current.id or file.user_id == current.id,
        }
        for c, name in rows
    ]


@router.post("/files/{file_id}/comments", status_code=201)
def add_comment(
    file_id: UUID,
    data: CommentRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file = require_file(db, current, file_id, PermissionRole.COMMENTER)
    body = data.body.strip()
    if not body:
        raise HTTPException(422, "Comment cannot be blank.")
    comment = Comment(file_id=file_id, user_id=current.id, body=body)
    db.add(comment)
    if current.id != file.user_id:
        db.add(
            Notification(
                user_id=file.user_id,
                file_id=file_id,
                kind="comment",
                message=f"A new comment was added to {file.original_name[:200]}.",
            )
        )
    db.commit()
    return {"id": comment.id}


@router.delete("/files/{file_id}/comments/{comment_id}", status_code=204)
def remove_comment(
    file_id: UUID,
    comment_id: UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file = require_file(db, current, file_id)
    comment = db.get(Comment, comment_id)
    if comment is None or comment.file_id != file_id:
        raise HTTPException(404, "Comment not found.")
    if comment.user_id != current.id and file.user_id != current.id:
        raise HTTPException(403, "Only the author or file owner can delete a comment.")
    db.delete(comment)
    db.commit()


@router.get("/files/{file_id}/versions")
def list_versions(
    file_id: UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_file(db, current, file_id)
    rows = db.execute(
        select(File).where(File.version_of == file_id).order_by(File.created_at.desc())
    ).scalars()
    return [
        {
            "id": f.id,
            "size": f.size,
            "mime_type": f.mime_type,
            "original_name": f.original_name,
            "created_at": f.created_at,
        }
        for f in rows
    ]


def swap_version(db, file, source):
    # Both rows already own one storage reference and their sizes are charged to
    # the same user. Swapping preserves reference counts and total quota usage.
    fields = (
        "stored_name",
        "mime_type",
        "size",
        "content_sha256",
        "storage_backend",
        "scan_status",
        "blob_id",
        "storage_path",
    )
    for field in fields:
        old = getattr(file, field)
        setattr(file, field, getattr(source, field))
        setattr(source, field, old)
    file.index_lease = None
    source.index_lease = None
    file.index_status = "PENDING"
    file.index_error = None
    source.version_of = file.id
    source.folder_id = None
    # A previous URL or permission on the incoming file must never start serving
    # a different payload after this swap.
    db.execute(
        update(SharedFile)
        .where(SharedFile.file_id == source.id)
        .values(is_active=False)
    )
    db.execute(
        delete(Permission).where(
            Permission.resource_type == ResourceType.FILE,
            Permission.resource_id == source.id,
        )
    )
    db.execute(
        text("DELETE FROM file_search_documents WHERE file_id IN (:original, :source)"),
        {"original": file.id, "source": source.id},
    )
    db.commit()
    enqueue_file_index(file.id)


@router.post("/files/{file_id}/versions", status_code=201)
def add_version(
    file_id: UUID,
    data: VersionRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_file(db, current, file_id, PermissionRole.OWNER)
    if file_id == data.source_file_id:
        raise HTTPException(400, "Choose a different uploaded file.")
    # Lock in a stable order for concurrent replacements.
    rows = (
        db.execute(
            select(File)
            .where(File.id.in_([file_id, data.source_file_id]))
            .order_by(File.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        .scalars()
        .all()
    )
    lookup = {f.id: f for f in rows}
    file, source = lookup.get(file_id), lookup.get(data.source_file_id)
    if (
        not file
        or not source
        or file.user_id != current.id
        or source.user_id != current.id
    ):
        raise HTTPException(404, "File not found.")
    if file.is_deleted or source.is_deleted or file.version_of or source.version_of:
        raise HTTPException(409, "Choose active files.")
    if file.scan_status != "CLEAN" or source.scan_status != "CLEAN":
        raise HTTPException(409, "Wait for both files to finish scanning.")
    swap_version(db, file, source)
    return {"version_id": source.id}


@router.post("/files/{file_id}/versions/{version_id}/restore", status_code=204)
def restore_version(
    file_id: UUID,
    version_id: UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_file(db, current, file_id, PermissionRole.OWNER)
    rows = (
        db.execute(
            select(File)
            .where(File.id.in_([file_id, version_id]))
            .order_by(File.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        .scalars()
        .all()
    )
    lookup = {f.id: f for f in rows}
    file, source = lookup.get(file_id), lookup.get(version_id)
    if (
        not file
        or not source
        or source.version_of != file_id
        or file.user_id != current.id
    ):
        raise HTTPException(404, "Version not found.")
    if file.is_deleted or file.scan_status != "CLEAN" or source.scan_status != "CLEAN":
        raise HTTPException(409, "Only clean, active files can be restored.")
    swap_version(db, file, source)


@router.get("/files/{file_id}/preview")
def preview_file(
    file_id: UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file, path = FileService(db).download_file(file_id=file_id, user=current)
    allowed = {"image/png", "image/jpeg", "image/webp", "application/pdf", "text/plain"}
    if file.mime_type not in allowed:
        raise HTTPException(
            415, "Preview supports PDF, plain text, PNG, JPEG, and WebP files."
        )
    if isinstance(path, str):
        return RedirectResponse(path, status_code=303)
    return FileResponse(
        path,
        filename=file.original_name,
        media_type=file.mime_type,
        content_disposition_type="inline",
        headers={
            "Content-Security-Policy": "sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/notifications")
def notifications(
    after: int = Query(0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Notification)
        .where(Notification.user_id == current.id, Notification.sequence > after)
        .order_by(Notification.sequence)
        .limit(100)
    ).scalars()
    return [
        {
            "sequence": n.sequence,
            "kind": n.kind,
            "message": n.message,
            "file_id": n.file_id,
            "created_at": n.created_at,
        }
        for n in rows
    ]


@router.get("/notifications/stream")
async def notification_stream(
    request: Request,
    after: int = Query(0, ge=0),
    current: User = Depends(get_stream_user),
):
    user_id, auth_version = current.id, current.auth_version
    from app.core.jwt import decode_token
    import time

    payload = decode_token(request.headers.get("authorization", "").split(" ", 1)[-1])
    expires, jti = payload["exp"], UUID(payload["jti"])

    async def events():
        cursor = after
        # Short lived streams reauthenticate on reconnect. No DB transaction or
        # SQLAlchemy Session is held while waiting between events.
        for _ in range(25):
            if time.time() >= expires or await request.is_disconnected():
                return

            def read_events():
                with SessionLocal() as db:
                    user = db.get(User, user_id)
                    if (
                        not user
                        or not user.is_active
                        or user.auth_version != auth_version
                    ):
                        return None
                    from app.db.models.token_blocklist import TokenBlocklist

                    if db.execute(
                        select(TokenBlocklist).where(TokenBlocklist.jti == jti)
                    ).scalar_one_or_none():
                        return None
                    return list(
                        db.execute(
                            select(Notification)
                            .where(
                                Notification.user_id == user_id,
                                Notification.sequence > cursor,
                            )
                            .order_by(Notification.sequence)
                            .limit(100)
                        ).scalars()
                    )

            from starlette.concurrency import run_in_threadpool

            rows = await run_in_threadpool(read_events)
            if rows is None:
                return
            for row in rows:
                cursor = row.sequence
                yield f"id: {cursor}\ndata: {json.dumps({'sequence': cursor, 'kind': row.kind, 'message': row.message, 'file_id': str(row.file_id) if row.file_id else None})}\n\n"
            yield ": heartbeat\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
