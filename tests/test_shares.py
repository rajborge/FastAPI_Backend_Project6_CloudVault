from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.core.enum import ShareExpiry
from app.core.exceptions import ShareDownloadLimitExceeded, ShareLinkExpired
from app.services.shared_file_service import SharedFileService


def test_share_expiry_options_calculate_expected_dates():
    service = SharedFileService.__new__(SharedFileService)
    now = datetime.now(timezone.utc)

    assert service._calculate_expiry(expiry=ShareExpiry.NEVER) is None
    assert service._calculate_expiry(expiry=ShareExpiry.ONE_DAY) <= now + timedelta(days=1, seconds=1)
    assert service._calculate_expiry(expiry=ShareExpiry.SEVEN_DAYS) <= now + timedelta(days=7, seconds=1)
    assert service._calculate_expiry(expiry=ShareExpiry.THIRTY_DAYS) <= now + timedelta(days=30, seconds=1)


def test_download_limit_deactivates_share_before_an_extra_download():
    service = SharedFileService.__new__(SharedFileService)
    share = SimpleNamespace(
        is_active=True,
        expires_at=None,
        password_hash=None,
        max_downloads=2,
        download_count=2,
    )
    service.shared_file_repository = Mock()
    service.shared_file_repository.get_by_token_for_update.return_value = share
    service.db = Mock()

    with pytest.raises(ShareDownloadLimitExceeded):
        service.get_shared_file(token="token", password=None)

    assert share.is_active is False
    service.db.commit.assert_called_once()


def test_shared_download_increments_count_after_clean_file_check(tmp_path):
    service = SharedFileService.__new__(SharedFileService)
    payload = tmp_path / "shared.pdf"
    payload.write_bytes(b"clean")
    share = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        expires_at=None,
        password_hash=None,
        max_downloads=3,
        download_count=0,
        file_id=uuid4(),
    )
    file = SimpleNamespace(
        id=share.file_id,
        is_deleted=False,
        scan_status="CLEAN",
        storage_backend="local",
        storage_path=str(payload),
        original_name="shared.pdf",
        mime_type="application/pdf",
    )
    service.shared_file_repository = Mock()
    service.shared_file_repository.get_by_token_for_update.return_value = share
    service.file_repository = Mock()
    service.file_repository.get_by_id.return_value = file
    service.storage_service = Mock()
    service.storage_service.get_file_path.return_value = Path(payload)
    service.db = Mock()

    result_file, result_path = service.get_shared_file(token="token", password=None)

    assert result_file is file
    assert result_path == payload
    assert share.download_count == 1
    service.db.commit.assert_called_once()
