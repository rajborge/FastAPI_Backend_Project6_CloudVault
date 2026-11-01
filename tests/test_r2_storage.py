from unittest.mock import Mock

import boto3
import pytest
from botocore.exceptions import ClientError

from app.services.r2_storage_service import R2StorageService


DIGEST = "a" * 64


def test_boto3_presigns_content_length_and_conditional_put():
    client = boto3.client(
        "s3",
        endpoint_url="https://account.r2.cloudflarestorage.com",
        aws_access_key_id="test-key",
        aws_secret_access_key="test-secret",
        region_name="auto",
    )
    storage = R2StorageService(client=client, bucket_name="vault")

    url = storage.create_upload_url(
        object_key="users/123/file",
        content_type="application/pdf",
        content_sha256=DIGEST,
        content_length=25,
    )

    assert "X-Amz-Signature=" in url
    assert "content-length" in url.lower()


def test_presigned_put_binds_content_type_and_digest():
    client = Mock()
    client.generate_presigned_url.return_value = "https://r2.test/upload"
    storage = R2StorageService(client=client, bucket_name="vault")

    url = storage.create_upload_url(
        object_key="users/123/file",
        content_type="application/pdf",
        content_sha256=DIGEST,
        content_length=25,
    )

    assert url == "https://r2.test/upload"
    client.generate_presigned_url.assert_called_once_with(
        "put_object",
        Params={
            "Bucket": "vault",
            "Key": "users/123/file",
            "ContentType": "application/pdf",
            "ContentLength": 25,
            "Metadata": {"sha256": DIGEST},
            "IfNoneMatch": "*",
        },
        ExpiresIn=600,
        HttpMethod="PUT",
    )


def test_multipart_completion_sorts_parts_and_verifies_object():
    client = Mock()
    client.head_object.side_effect = [
        ClientError({"Error": {"Code": "404"}}, "HeadObject"),
        {
            "ContentLength": 9,
            "ContentType": "application/octet-stream",
            "Metadata": {"sha256": DIGEST},
            "ETag": "etag",
        },
    ]
    storage = R2StorageService(client=client, bucket_name="vault")

    result = storage.complete_multipart_upload(
        object_key="users/123/file",
        upload_id="upload-1",
        parts=[
            {"PartNumber": 2, "ETag": "part-2"},
            {"PartNumber": 1, "ETag": "part-1"},
        ],
    )

    assert result == {
        "size": 9,
        "content_type": "application/octet-stream",
        "content_sha256": DIGEST,
        "etag": "etag",
    }
    client.complete_multipart_upload.assert_called_once_with(
        Bucket="vault",
        Key="users/123/file",
        UploadId="upload-1",
        MultipartUpload={
            "Parts": [
                {"PartNumber": 1, "ETag": "part-1"},
                {"PartNumber": 2, "ETag": "part-2"},
            ]
        },
    )


def test_invalid_part_number_and_digest_are_rejected():
    client = Mock()
    storage = R2StorageService(client=client, bucket_name="vault")

    with pytest.raises(ValueError):
        storage.create_part_upload_url(
            object_key="users/123/file",
            upload_id="upload-1",
            part_number=10_001,
            content_length=1,
        )

    with pytest.raises(ValueError):
        storage.create_upload_url(
            object_key="users/123/file",
            content_type="application/pdf",
            content_sha256="invalid",
            content_length=1,
        )

    client.generate_presigned_url.assert_not_called()
