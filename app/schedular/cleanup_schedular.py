from apscheduler.schedulers.background import BackgroundScheduler

from ..db.database import SessionLocal
from ..services.file_service import FileService
from ..services.upload_intent_service import UploadIntentService
from ..core.config import settings

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


def cleanup_upload_intents_job():
    if not settings.R2_BUCKET_NAME:
        return

    db=SessionLocal()
    try:
        cleaned=UploadIntentService(db).cleanup_expired_intents()
        logger.info("Expired upload intents cleaned up: %d", cleaned)
    except Exception:
        logger.exception("Expired upload intent cleanup failed.")
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

schedular.add_job(
    cleanup_upload_intents_job,
    trigger="interval",
    hours=1,
    id="cleanup_upload_intents_job",
    max_instances=1,
    coalesce=True,
    misfire_grace_time=60,
    replace_existing=True,
)

def start_schedular():
    if not schedular.running:
        schedular.start()
        logger.info("Cleanup scheduler started.")


def stop_schedular():
    if schedular.running:
        schedular.shutdown(wait=False)
        logger.info("Cleanup scheduler stopped.")
