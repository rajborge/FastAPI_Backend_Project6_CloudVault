from celery import Celery

from .config import settings

# Import the complete SQLAlchemy model registry before Celery forks workers.
# This is required for string relationships such as File -> SharedFile.
import app.db.base  # noqa: F401, E402


celery_app = Celery(
    "cloudvault",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.file_task"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_soft_time_limit=840,
    task_time_limit=900,
    worker_max_memory_per_child=512 * 1024,
)
