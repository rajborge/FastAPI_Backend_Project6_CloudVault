import logging
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from app.core.celery_app import celery_app
from app.db.database import SessionLocal
from app.repositories.file_repository import FileRepository
from app.repositories.storage_blob_repository import StorageBlobRepository
from app.services.clamav_service import ClamAVService
from app.services.r2_storage_service import R2StorageService
from app.services.search_service import hashed_text_vector, vector_literal


logger = logging.getLogger("cloudvault.tasks.file")


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
    acks_late=True,
)
def scan_file_task(self, file_id: str) -> str:
    db = SessionLocal()
    repository = FileRepository(db)
    blob_repository = StorageBlobRepository(db)

    try:
        file = repository.get_by_id_for_update(UUID(file_id))
        if file is None or file.scan_status not in {"PENDING_SCAN", "SCANNING"}:
            return "skipped"

        file.scan_status = "SCANNING"
        db.commit()

        try:
            scanner = ClamAVService()

            if file.storage_backend == "r2":
                stream = R2StorageService().get_object_stream(
                    object_key=file.storage_path,
                )
                try:
                    scan_status, content_sha256 = scanner.scan_stream(stream)
                finally:
                    stream.close()
            else:
                with Path(file.storage_path).open("rb") as stream:
                    scan_status, content_sha256 = scanner.scan_stream(stream)

            file = repository.get_by_id_for_update(UUID(file_id))
            if file is None or file.scan_status in {"CLEAN", "INFECTED"}:
                return "skipped"

            duplicate_object_key = None
            original_backend = file.storage_backend

            if scan_status == "INFECTED":
                if file.storage_backend == "r2":
                    R2StorageService().delete_object(object_key=file.storage_path)
                else:
                    Path(file.storage_path).unlink(missing_ok=True)

                file.user.storage_used = max(
                    0,
                    file.user.storage_used - file.size,
                )
            else:
                _, duplicate_object_key = blob_repository.attach_clean_file(
                    file=file,
                    content_sha256=content_sha256,
                )

            file.scan_status = scan_status
            file.content_sha256 = content_sha256
            db.commit()

            if duplicate_object_key is not None:
                try:
                    if original_backend == "r2":
                        R2StorageService().delete_object(
                            object_key=duplicate_object_key,
                        )
                    else:
                        Path(duplicate_object_key).unlink(missing_ok=True)
                except Exception:
                    logger.exception(
                        "Failed to remove duplicate payload: file_id=%s",
                        file_id,
                    )

            logger.info(
                "File scan completed: file_id=%s status=%s",
                file_id,
                scan_status,
            )
            return scan_status

        except Exception:
            db.rollback()
            file = repository.get_by_id_for_update(UUID(file_id))
            if file is not None and file.scan_status == "SCANNING":
                file.scan_status = "PENDING_SCAN"
                db.commit()
            raise
    finally:
        db.close()


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    acks_late=True,
)
def index_file_task(self, file_id: str) -> str:
    db = SessionLocal()
    repository = FileRepository(db)

    try:
        file = repository.get_by_id(UUID(file_id))
        if file is None or file.is_deleted or file.scan_status != "CLEAN":
            return "skipped"

        payload = _read_payload(file)
        extracted_text = _extract_text(payload, file.mime_type).strip()

        # Filename is intentionally included in the vector so filename search and
        # content search both participate in the hybrid search endpoint.
        searchable_text = f"{file.original_name}\n{extracted_text}".strip()
        embedding = vector_literal(hashed_text_vector(searchable_text))

        db.execute(
            text(
                """
                INSERT INTO file_search_documents (
                    file_id,
                    extracted_text,
                    embedding,
                    indexed_at
                ) VALUES (
                    :file_id,
                    :extracted_text,
                    CAST(:embedding AS vector),
                    :indexed_at
                )
                ON CONFLICT (file_id) DO UPDATE SET
                    extracted_text = EXCLUDED.extracted_text,
                    embedding = EXCLUDED.embedding,
                    indexed_at = EXCLUDED.indexed_at
                """
            ),
            {
                "file_id": file.id,
                "extracted_text": extracted_text,
                "embedding": embedding,
                "indexed_at": datetime.now(timezone.utc),
            },
        )
        db.commit()

        logger.info(
            "File indexed: file_id=%s mime=%s chars=%s",
            file_id,
            file.mime_type,
            len(extracted_text),
        )
        return "indexed"
    except Exception:
        db.rollback()
        logger.exception("File indexing failed: file_id=%s", file_id)
        raise
    finally:
        db.close()


@celery_app.task
def index_after_scan_task(scan_status: str, file_id: str) -> str:
    if scan_status != "CLEAN":
        return "skipped"

    index_file_task.delay(file_id)
    return "queued"


def enqueue_file_scan(file_id: UUID) -> None:
    try:
        workflow = (
            scan_file_task.s(str(file_id))
            | index_after_scan_task.s(str(file_id))
        )
        workflow.delay()
    except Exception:
        logger.exception("Failed to enqueue file scan: file_id=%s", file_id)


def enqueue_file_index(file_id: UUID) -> None:
    try:
        index_file_task.delay(str(file_id))
    except Exception:
        logger.exception("Failed to enqueue file index: file_id=%s", file_id)


def _read_payload(file) -> bytes:
    if file.storage_backend == "r2":
        stream = R2StorageService().get_object_stream(
            object_key=file.storage_path,
        )
        try:
            return stream.read()
        finally:
            stream.close()

    return Path(file.storage_path).read_bytes()


def _extract_text(payload: bytes, mime_type: str) -> str:
    mime_type = (mime_type or "").lower()

    if mime_type.startswith("text/"):
        return payload.decode("utf-8", errors="ignore")

    if mime_type == "application/pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(payload))
            return "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )
        except Exception:
            logger.exception("PDF text extraction failed")
            return ""

    if mime_type.startswith("image/"):
        try:
            import pytesseract
            from PIL import Image, ImageOps

            image = Image.open(BytesIO(payload))
            image = ImageOps.exif_transpose(image)

            # Tesseract is generally more stable with a standard color mode.
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")

            return pytesseract.image_to_string(image)
        except Exception:
            logger.exception("Image OCR failed")
            return ""

    # Unsupported binary formats are still indexed by filename because the
    # caller includes file.original_name in searchable_text.
    return ""
