from apscheduler.schedulers.background import BackgroundScheduler

from ..db.database import SessionLocal
from ..services.file_service import FileService

import logging

logger=logging.getLogger("cloudvault.schedular")

schedular=BackgroundScheduler()

def cleanup_job():
    logger.info("Running expired file cleanup.")
    db=SessionLocal()

    try:
        service=FileService(db)

        deleted=service.cleanup_expired_files()

        logger.info(
        "Cleanup completed. Deleted %d expired file(s).",
        deleted,
    )
        
    except Exception:
        logger.exception(
            "Cleanup job failed."
        )

    finally:
        db.close()

schedular.add_job(
    cleanup_job,
    trigger="cron",
    hour=2,
    minute=0,
    timezone="UTC",
    id="cleanup_job",
    max_instances=1,
    coalesce=True,
    misfire_grace_time=60,
    replace_existing=True
)

def start_schedular():
    if not schedular.running:
        schedular.start()
        logger.info("Cleanup scheduler started.")
