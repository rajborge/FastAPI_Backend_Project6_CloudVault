import re
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from ..core.config import settings
from ..core.exceptions import ObjectStorageConfigurationException


class R2StorageService:
    def __init__(self, client: Any | None = None, bucket_name: str | None = None):
        self.bucket_name = bucket_name or settings.R2_BUCKET_NAME
        if not self.bucket_name:
            raise ObjectStorageConfigurationException()

        if client is not None:
            self.client = client
            return

        required_settings = {
            "R2_ENDPOINT_URL": settings.R2_ENDPOINT_URL,
            "R2_ACCESS_KEY_ID": settings.R2_ACCESS_KEY_ID,
            "R2_SECRET_ACCESS_KEY": settings.R2_SECRET_ACCESS_KEY,
        }
        missing_settings = [
            name for name, value in required_settings.items() if not value
        ]
        if missing_settings:
            raise ObjectStorageConfigurationException()

        self.client = boto3.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )

    def create_upload_url(
        self,
        *,
        object_key: str,
        content_type: str,
        content_sha256: str,
        content_length: int,
        expires_in: int | None = None,
    ) -> str:
        self._validate_object_metadata(object_key, content_sha256)
        return self.client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": object_key,
                "ContentType": content_type,
                "ContentLength": content_length,
                "Metadata": {"sha256": content_sha256},
                "IfNoneMatch": "*",
            },
            ExpiresIn=expires_in or settings.R2_PRESIGNED_URL_TTL_SECONDS,
            HttpMethod="PUT",
        )

    def create_multipart_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        content_sha256: str,
    ) -> str:
        self._validate_object_metadata(object_key, content_sha256)
        response = self.client.create_multipart_upload(
            Bucket=self.bucket_name,
            Key=object_key,
            ContentType=content_type,
            Metadata={"sha256": content_sha256},
        )
        return response["UploadId"]

    def create_part_upload_url(
        self,
        *,
        object_key: str,
        upload_id: str,
        part_number: int,
        content_length: int,
        expires_in: int | None = None,
    ) -> str:
        if not 1 <= part_number <= 10_000:
            raise ValueError("Multipart part number must be between 1 and 10000")

        return self.client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": self.bucket_name,
                "Key": object_key,
                "UploadId": upload_id,
                "PartNumber": part_number,
                "ContentLength": content_length,
            },
            ExpiresIn=expires_in or settings.R2_PRESIGNED_URL_TTL_SECONDS,
            HttpMethod="PUT",
        )

    def complete_multipart_upload(
        self,
        *,
        object_key: str,
        upload_id: str,
        parts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not parts:
            raise ValueError("At least one completed part is required")

        existing_object = self.head_object_if_exists(object_key=object_key)
        if existing_object is not None:
            return existing_object

        normalized_parts = sorted(parts, key=lambda part: part["PartNumber"])
        self.client.complete_multipart_upload(
            Bucket=self.bucket_name,
            Key=object_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": normalized_parts},
        )
        return self.head_object(object_key=object_key)

    def head_object_if_exists(self, *, object_key: str) -> dict[str, Any] | None:
        try:
            return self.head_object(object_key=object_key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise

    def abort_multipart_upload(self, *, object_key: str, upload_id: str) -> None:
        self.client.abort_multipart_upload(
            Bucket=self.bucket_name,
            Key=object_key,
            UploadId=upload_id,
        )

    def head_object(self, *, object_key: str) -> dict[str, Any]:
        response = self.client.head_object(Bucket=self.bucket_name, Key=object_key)
        return {
            "size": response["ContentLength"],
            "content_type": response.get("ContentType"),
            "content_sha256": response.get("Metadata", {}).get("sha256"),
            "etag": response.get("ETag"),
        }

    def create_download_url(
        self,
        *,
        object_key: str,
        expires_in: int | None = None,
        filename: str | None = None,
        content_type: str | None = None,
        inline: bool = False,
    ) -> str:
        params = {"Bucket": self.bucket_name, "Key": object_key}
        if filename:
            from urllib.parse import quote

            params["ResponseContentDisposition"] = (
                f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{quote(filename, safe='')}"
            )
        if content_type:
            params["ResponseContentType"] = content_type
        return self.client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires_in or settings.R2_PRESIGNED_URL_TTL_SECONDS,
            HttpMethod="GET",
        )

    def get_object_stream(self, *, object_key: str):
        response = self.client.get_object(Bucket=self.bucket_name, Key=object_key)
        return response["Body"]

    def delete_object(self, *, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket_name, Key=object_key)

    def list_uploaded_parts(self, *, object_key: str, upload_id: str) -> list[dict]:
        parts, marker = [], 0
        while True:
            response = self.client.list_parts(
                Bucket=self.bucket_name,
                Key=object_key,
                UploadId=upload_id,
                PartNumberMarker=marker,
            )
            parts.extend(
                {"part_number": p["PartNumber"], "etag": p["ETag"]}
                for p in response.get("Parts", [])
            )
            if not response.get("IsTruncated"):
                return parts
            marker = response["NextPartNumberMarker"]

    @staticmethod
    def _validate_object_metadata(object_key: str, content_sha256: str) -> None:
        if not object_key:
            raise ValueError("Object key cannot be empty")
        if re.fullmatch(r"[0-9a-fA-F]{64}", content_sha256) is None:
            raise ValueError("content_sha256 must be a 64-character hex digest")
