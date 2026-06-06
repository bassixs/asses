from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from bot.config import settings

logger = logging.getLogger(__name__)


class ObjectStorageError(RuntimeError):
    pass


def _require_storage_settings() -> tuple[str, str, str]:
    if not settings.yandex_storage_bucket:
        raise ObjectStorageError("YANDEX_STORAGE_BUCKET is not configured")
    if not settings.yandex_storage_access_key_id:
        raise ObjectStorageError("YANDEX_STORAGE_ACCESS_KEY_ID is not configured")
    if not settings.yandex_storage_secret_access_key:
        raise ObjectStorageError("YANDEX_STORAGE_SECRET_ACCESS_KEY is not configured")
    return (
        settings.yandex_storage_bucket,
        settings.yandex_storage_access_key_id,
        settings.yandex_storage_secret_access_key,
    )


def _storage_client():
    _, access_key_id, secret_access_key = _require_storage_settings()
    session = boto3.session.Session()
    return session.client(
        service_name="s3",
        endpoint_url=settings.yandex_storage_endpoint,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="ru-central1",
    )


def _build_object_key(file_path: Path) -> str:
    prefix = settings.yandex_storage_prefix.strip("/")
    safe_name = file_path.name.replace("\\", "_").replace("/", "_")
    return f"{prefix}/{safe_name}" if prefix else safe_name


def build_object_key_for_file_path(file_path: str | Path | None) -> str | None:
    if not file_path:
        return None
    return _build_object_key(Path(file_path))


def _upload_file_sync(file_path: Path, object_key: str) -> None:
    bucket, _, _ = _require_storage_settings()
    client = _storage_client()
    try:
        client.upload_file(str(file_path), bucket, object_key)
    except (BotoCoreError, ClientError) as exc:
        raise ObjectStorageError(f"Object Storage upload failed: {exc}") from exc


async def upload_file_for_speechkit(file_path: Path) -> str:
    """Upload a file to Yandex Object Storage and return its HTTPS URL."""
    bucket, _, _ = _require_storage_settings()
    object_key = _build_object_key(file_path)
    logger.info("Uploading file to Object Storage: bucket=%s key=%s", bucket, object_key)
    await asyncio.to_thread(_upload_file_sync, file_path, object_key)
    return f"{settings.yandex_storage_endpoint.rstrip('/')}/{bucket}/{object_key}"


def _delete_object_sync(object_key: str) -> None:
    bucket, _, _ = _require_storage_settings()
    client = _storage_client()
    try:
        client.delete_object(Bucket=bucket, Key=object_key)
    except (BotoCoreError, ClientError) as exc:
        raise ObjectStorageError(f"Object Storage delete failed: {exc}") from exc


async def delete_object_by_key(object_key: str | None) -> bool:
    if not object_key:
        return False
    logger.info("Deleting Object Storage item: bucket=%s key=%s", settings.yandex_storage_bucket, object_key)
    await asyncio.to_thread(_delete_object_sync, object_key)
    return True


async def delete_uploaded_file_from_storage(file_path: str | Path | None) -> bool:
    return await delete_object_by_key(build_object_key_for_file_path(file_path))


def _delete_prefix_sync(prefix: str) -> int:
    bucket, _, _ = _require_storage_settings()
    client = _storage_client()
    deleted_count = 0

    try:
        continuation_token: str | None = None
        while True:
            request: dict[str, object] = {"Bucket": bucket, "Prefix": prefix}
            if continuation_token:
                request["ContinuationToken"] = continuation_token

            response = client.list_objects_v2(**request)
            objects = [{"Key": item["Key"]} for item in response.get("Contents", []) if "Key" in item]
            if objects:
                client.delete_objects(Bucket=bucket, Delete={"Objects": objects, "Quiet": True})
                deleted_count += len(objects)

            if not response.get("IsTruncated"):
                return deleted_count
            continuation_token = response.get("NextContinuationToken")
    except (BotoCoreError, ClientError) as exc:
        raise ObjectStorageError(f"Object Storage prefix cleanup failed: {exc}") from exc


async def delete_uploaded_prefix_from_storage() -> int:
    prefix = settings.yandex_storage_prefix.strip("/")
    if not prefix:
        logger.warning("Skipping Object Storage prefix cleanup because YANDEX_STORAGE_PREFIX is empty")
        return 0
    if prefix:
        prefix = f"{prefix}/"
    logger.info("Deleting Object Storage prefix: bucket=%s prefix=%s", settings.yandex_storage_bucket, prefix)
    return await asyncio.to_thread(_delete_prefix_sync, prefix)
