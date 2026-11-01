"""Reconcile durable database state with tasks lost during broker/worker outages."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models.file import File
from app.tasks.file_task import enqueue_file_index, enqueue_file_scan


def recover_jobs() -> dict:
    now = datetime.now(timezone.utc)
    retry_before = now - timedelta(minutes=2)
    abandoned = now - timedelta(seconds=max(900, settings.CLAMAV_TIMEOUT_SECONDS * 3))
    counts = {"scan": 0, "index": 0}
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(File)
                .where(
                    File.version_of.is_(None),
                    File.is_deleted.is_(False),
                    or_(
                        (File.scan_status == "PENDING_SCAN")
                        & (File.updated_at < retry_before),
                        (File.scan_status == "SCANNING")
                        & (File.scan_started_at < abandoned),
                        (File.scan_status == "CLEAN")
                        & File.index_status.in_(["PENDING", "INDEXING"])
                        & (File.updated_at < abandoned),
                    ),
                )
                .order_by(File.id)
                .limit(100)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
            .scalars()
            .all()
        )
        dispatch = []
        for file in rows:
            kind = "index" if file.scan_status == "CLEAN" else "scan"
            if kind == "scan":
                file.scan_status = "PENDING_SCAN"
                file.scan_lease = None
                file.scan_started_at = None
            else:
                file.index_status = "PENDING"
                file.index_lease = None
            file.updated_at = now
            dispatch.append((kind, file.id))
        # Commit the retry timestamp before dispatch; failed dispatch remains
        # eligible on the next sweep. Duplicate scan tasks are lease-guarded.
        db.commit()
    for kind, file_id in dispatch:
        queued = (
            enqueue_file_scan(file_id)
            if kind == "scan"
            else enqueue_file_index(file_id)
        )
        counts[kind] += int(bool(queued))
    return counts
