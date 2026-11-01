from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.tasks import file_task as file_task_module


@pytest.mark.parametrize(
    ("verdict", "expected_usage"),
    [("CLEAN", 20), ("INFECTED", 6)],
)
def test_scan_task_updates_file_state_and_usage(
    tmp_path,
    monkeypatch,
    verdict,
    expected_usage,
):
    content = b"test file data"
    file_path = tmp_path / "payload.bin"
    file_path.write_bytes(content)
    file = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        original_name="payload.bin",
        scan_status="PENDING_SCAN",
        storage_backend="local",
        storage_path=str(file_path),
        size=len(content),
        content_sha256=None,
        user=SimpleNamespace(storage_used=20),
    )
    repository = Mock()
    repository.get_by_id_for_update.side_effect = [file, file]
    blob_repository = Mock()
    blob_repository.attach_clean_file.return_value = (
        SimpleNamespace(
            id=uuid4(),
            storage_backend="local",
            object_key=str(file_path),
        ),
        None,
    )
    database = Mock()
    scanner = Mock()
    scanner.scan_stream.return_value = (verdict, sha256(content).hexdigest())

    monkeypatch.setattr(file_task_module, "SessionLocal", lambda: database)
    monkeypatch.setattr(file_task_module, "FileRepository", lambda db: repository)
    monkeypatch.setattr(
        file_task_module,
        "StorageBlobRepository",
        lambda db: blob_repository,
    )
    monkeypatch.setattr(file_task_module, "ClamAVService", lambda: scanner)
    user_repository = Mock()
    def release_storage(user_id, size):
        file.user.storage_used -= size
    user_repository.release_storage.side_effect = release_storage
    monkeypatch.setattr(file_task_module, "UserRepository", lambda db: user_repository)

    result = file_task_module.scan_file_task.run(str(file.id))

    assert result == verdict
    assert file.scan_status == verdict
    assert file.content_sha256 == sha256(content).hexdigest()
    assert file.user.storage_used == expected_usage
    assert database.commit.call_count == 2
    assert file_path.exists() is (verdict == "CLEAN")
    assert blob_repository.attach_clean_file.call_count == (verdict == "CLEAN")
    database.close.assert_called_once()
