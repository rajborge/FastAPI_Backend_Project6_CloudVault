from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock,call
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.core.exceptions import StorageQuotaExceededException
from app.services import file_service as file_service_module
from app.services.file_service import FileService
from app.services.storage_service import StorageService


def test_save_file_measures_and_hashes_actual_content(tmp_path):
	content=b"actual file content"
	upload=UploadFile(file=BytesIO(content),filename="receipt.pdf")
	storage=StorageService()
	storage.upload_dir=tmp_path

	stored_name,storage_path,size,content_sha256=storage.save_file(
		upload,
		max_bytes=len(content),
	)

	assert size==len(content)
	assert content_sha256==sha256(content).hexdigest()
	assert (tmp_path/stored_name).read_bytes()==content
	assert storage_path==str(tmp_path/stored_name)


def test_save_file_removes_partial_file_when_limit_is_exceeded(tmp_path):
	content=b"larger than allowed"
	upload=UploadFile(file=BytesIO(content),filename="large.bin")
	storage=StorageService()
	storage.upload_dir=tmp_path

	with pytest.raises(StorageQuotaExceededException):
		storage.save_file(upload,max_bytes=len(content)-1)

	assert list(tmp_path.iterdir())==[]


def test_upload_persists_measured_size_and_hash(monkeypatch):
	content=b"real content"
	monkeypatch.setattr(file_service_module,"enqueue_file_scan",Mock())
	monkeypatch.setattr(
		file_service_module,
		"File",
		lambda **values: SimpleNamespace(id=uuid4(),**values),
	)
	upload=UploadFile(file=BytesIO(content),filename="receipt.pdf")
	upload.size=1
	user=SimpleNamespace(
		id=uuid4(),
		storage_used=3,
		storage_reserved=0,
		storage_limit=100,
	)
	service=FileService.__new__(FileService)
	service.db=Mock()
	service.file_repository=Mock()
	service.user_repository=Mock()
	service.user_repository.get_by_id_for_update.return_value=user
	service.folder_repository=Mock()
	service.audit_service=Mock()
	service.storage_service=Mock()
	service.storage_service.save_file.return_value=(
		"stored-name",
		"uploads/stored-name",
		len(content),
		sha256(content).hexdigest(),
	)

	uploaded=service.upload_file(
		upload_file=upload,
		user=user,
		folder_id=None,
	)

	assert uploaded.size==len(content)
	assert uploaded.content_sha256==sha256(content).hexdigest()
	assert user.storage_used==3+len(content)
	service.storage_service.save_file.assert_called_once_with(
		upload,
		max_bytes=97,
	)


def test_storage_quota_includes_reserved_upload_bytes():
	service=FileService.__new__(FileService)
	user=SimpleNamespace(storage_used=10,storage_reserved=70,storage_limit=100)

	with pytest.raises(StorageQuotaExceededException):
		service.check_storage_quota(user=user,file_size=21)


def test_manual_cleanup_is_user_scoped_but_scheduled_cleanup_is_global():
	service=FileService.__new__(FileService)
	service.db=Mock()
	service.file_repository=Mock()
	service.file_repository.get_expired_deleted_files.return_value=[]
	service.storage_service=Mock()
	user=SimpleNamespace(id=uuid4())

	assert service.cleanup_expired_files(user=user)==0
	assert service.cleanup_expired_files()==0

	assert service.file_repository.get_expired_deleted_files.call_args_list==[
		call(user_id=user.id),
		call(user_id=None),
	]
