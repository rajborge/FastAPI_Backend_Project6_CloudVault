import logging
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.core.privacy import CapabilityFilter, redact_path
from app.tasks import file_task


def test_capabilities_are_redacted_in_application_and_uvicorn_access_logs():
    assert redact_path("/shares/secret/download") == "/shares/[redacted]/download"
    assert redact_path("/shares/share_file") == "/shares/share_file"
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %s',
        ("127.0.0.1", "GET", "/shares/secret?x=1", "1.1", 200),
        None,
    )
    CapabilityFilter().filter(record)
    assert "secret" not in record.getMessage()
    assert "[redacted]" in record.getMessage()


def test_duplicate_scan_task_does_not_touch_an_active_worker(monkeypatch):
    file = SimpleNamespace(scan_status="SCANNING", scan_lease=uuid4())
    db, repository, scanner = Mock(), Mock(), Mock()
    repository.get_by_id_for_update.return_value = file
    monkeypatch.setattr(file_task, "SessionLocal", lambda: db)
    monkeypatch.setattr(file_task, "FileRepository", lambda _: repository)
    monkeypatch.setattr(file_task, "ClamAVService", scanner)
    assert file_task.scan_file_task.run(str(uuid4())) == "skipped"
    scanner.assert_not_called()


def test_corrupt_pdf_extraction_is_visible_instead_of_silently_empty():
    with pytest.raises(Exception):
        file_task._extract_text(b"not a PDF", "application/pdf")


def test_scanned_pdf_pages_are_rendered_and_passed_to_ocr(monkeypatch):
    from io import BytesIO
    from pypdf import PdfWriter

    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    called = []

    def ocr(image):
        called.append(image.size)
        return "recognized page"

    monkeypatch.setattr(file_task, "_ocr_image", ocr)
    assert (
        file_task._extract_text(output.getvalue(), "application/pdf")
        == "recognized page"
    )
    assert called == [(144, 144)]
