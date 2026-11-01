import logging
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text
from app.core.config import settings
from app.db.models.collaboration import Notification
from app.repositories.user import UserRepository
from app.services.embedding_service import embed_text, model_name

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

        if file.scan_status == "SCANNING" and file.scan_lease is not None:
            return "skipped"
        lease = uuid4()
        file.scan_lease = lease
        file.scan_started_at = datetime.now(timezone.utc)
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
            if file is None or file.scan_lease != lease or file.scan_status in {"CLEAN", "INFECTED"}:
                return "skipped"

            duplicate_object_key = None
            original_backend = file.storage_backend

            if scan_status == "INFECTED":
                if file.storage_backend == "r2":
                    R2StorageService().delete_object(object_key=file.storage_path)
                else:
                    Path(file.storage_path).unlink(missing_ok=True)

                UserRepository(db).release_storage(file.user_id, file.size)
            else:
                _, duplicate_object_key = blob_repository.attach_clean_file(
                    file=file,
                    content_sha256=content_sha256,
                )

            file.scan_lease = None
            file.scan_started_at = None
            db.add(Notification(user_id=file.user_id, file_id=file.id, kind="scan",
                message=f"{file.original_name[:200]}: {scan_status.lower()}."))
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
            if file is not None and file.scan_status == "SCANNING" and file.scan_lease == lease:
                file.scan_status = "PENDING_SCAN"
                file.scan_lease = None
                file.scan_started_at = None
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
    index_lease = None

    try:
        file = repository.get_by_id_for_update(UUID(file_id))
        if file is None or file.is_deleted or file.scan_status != "CLEAN":
            return "skipped"

        index_lease = uuid4()
        file.index_lease = index_lease
        file.index_status = "INDEXING"
        file.index_error = None
        db.commit()
        payload = _read_payload(file)
        extracted_text = _extract_text(payload, file.mime_type).strip()

        # Filename is intentionally included in the vector so filename search and
        # content search both participate in the hybrid search endpoint.
        searchable_text = f"{file.original_name}\n{extracted_text}".strip()
        embedding = vector_literal(embed_text(searchable_text))

        file = repository.get_by_id_for_update(UUID(file_id))
        if file is None or file.is_deleted or file.version_of is not None or file.index_lease != index_lease:
            return "skipped"
        db.execute(
            text(
                """
                INSERT INTO file_search_documents (
                    file_id,
                    extracted_text,
                    embedding,
                    embedding_model,
                    indexed_at
                ) VALUES (
                    :file_id,
                    :extracted_text,
                    CAST(:embedding AS vector),
                    :embedding_model,
                    :indexed_at
                )
                ON CONFLICT (file_id) DO UPDATE SET
                    extracted_text = EXCLUDED.extracted_text,
                    embedding = EXCLUDED.embedding,
                    embedding_model = EXCLUDED.embedding_model,
                    indexed_at = EXCLUDED.indexed_at
                """
            ),
            {
                "file_id": file.id,
                "extracted_text": extracted_text,
                "embedding": embedding,
                "embedding_model": model_name(),
                "indexed_at": datetime.now(timezone.utc),
            },
        )
        file = repository.get_by_id_for_update(UUID(file_id))
        if file is not None:
            file.index_lease = None
            file.index_status = "READY"
            file.index_error = None
            db.add(Notification(user_id=file.user_id, file_id=file.id, kind="index", message="File search index is ready."))
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
        file = repository.get_by_id_for_update(UUID(file_id))
        if file is not None and file.index_lease == index_lease:
            file.index_lease = None
            file.index_status = "FAILED"
            file.index_error = "Text extraction or indexing failed. Retry indexing or contact the administrator."
            db.add(Notification(user_id=file.user_id, file_id=file.id, kind="index",
                message="File search indexing failed. Open file tools to retry."))
            db.commit()
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


def enqueue_file_scan(file_id: UUID) -> bool:
    try:
        workflow = (
            scan_file_task.s(str(file_id))
            | index_after_scan_task.s(str(file_id))
        )
        workflow.delay()
        return True
    except Exception:
        logger.error("Failed to enqueue file scan: file_id=%s; recovery will retry", file_id)
        return False


def enqueue_file_index(file_id: UUID) -> bool:
    try:
        index_file_task.delay(str(file_id))
        return True
    except Exception:
        logger.error("Failed to enqueue file index: file_id=%s; recovery will retry", file_id)
        return False


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
        return payload.decode("utf-8", errors="replace")[:2_000_000]
    if mime_type == "application/pdf":
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(payload))
        if len(reader.pages) > settings.OCR_MAX_PAGES:
            raise ValueError("PDF exceeds the configured page limit.")
        pages = []
        document = None
        try:
            for i, page in enumerate(reader.pages):
                extracted = page.extract_text() or ""
                if not extracted.strip():
                    import pypdfium2 as pdfium
                    if document is None:
                        document = pdfium.PdfDocument(payload)
                    pdf_page = document[i]
                    try:
                        width, height = pdf_page.get_size()
                        scale = min(2.0, (settings.OCR_MAX_PIXELS / max(1, width * height)) ** 0.5)
                        bitmap = pdf_page.render(scale=scale)
                        try:
                            extracted = _ocr_image(bitmap.to_pil())
                        finally:
                            bitmap.close()
                    finally:
                        pdf_page.close()
                pages.append(extracted)
        finally:
            if document is not None:
                document.close()
        return "\n".join(pages)[:2_000_000]
    if mime_type.startswith("image/"):
        from PIL import Image
        with Image.open(BytesIO(payload)) as image:
            if image.width * image.height > settings.OCR_MAX_PIXELS:
                raise ValueError("Image exceeds OCR pixel limit.")
            return _ocr_image(image)
    return ""


def _ocr_image(image) -> str:
    import pytesseract
    from PIL import ImageOps
    image = ImageOps.exif_transpose(image)
    if image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")
    return pytesseract.image_to_string(image, timeout=90)
