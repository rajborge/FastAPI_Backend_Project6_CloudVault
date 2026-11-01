from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.repositories.storage_blob_repository import StorageBlobRepository


def test_clean_file_reuses_blob_and_increments_reference_count():
    file = SimpleNamespace(
        id=uuid4(),
        storage_backend="r2",
        storage_path="users/1/new-object",
        size=100,
        blob_id=None,
    )
    blob = SimpleNamespace(
        id=uuid4(),
        storage_backend="r2",
        object_key="users/2/existing-object",
        content_sha256="a" * 64,
        size=100,
        reference_count=3,
    )
    query_result = Mock()
    query_result.scalar_one.return_value = blob
    database = Mock()
    database.execute.side_effect = [Mock(), query_result]

    attached_blob, duplicate_object_key = StorageBlobRepository(
        database
    ).attach_clean_file(file=file, content_sha256="a" * 64)

    assert attached_blob is blob
    assert blob.reference_count == 4
    assert file.blob_id == blob.id
    assert file.storage_path == blob.object_key
    assert duplicate_object_key == "users/1/new-object"


def test_blob_payload_is_only_released_for_last_reference():
    blob = SimpleNamespace(
        id=uuid4(),
        storage_backend="r2",
        object_key="users/shared/object",
        reference_count=2,
    )
    file = SimpleNamespace(
        blob_id=blob.id,
        storage_backend="r2",
        storage_path=blob.object_key,
    )
    database = Mock()
    database.execute.return_value.scalar_one_or_none.return_value = blob
    repository = StorageBlobRepository(database)

    assert repository.release_file_reference(file) is None
    assert blob.reference_count == 1
    database.delete.assert_not_called()

    blob.reference_count = 1
    payload = repository.release_file_reference(file)

    assert payload == ("r2", "users/shared/object")
    database.delete.assert_called_once_with(blob)
