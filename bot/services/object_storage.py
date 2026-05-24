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

