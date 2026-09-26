"""
Tool 01 — Log Ingestion Tool — Storage Layer
Abstracted S3-compatible object storage client.
Uploads raw log files to cloud object storage before processing begins.
"""
from __future__ import annotations

import asyncio
import io
import uuid
from typing import AsyncIterator

import aioboto3
from botocore.config import Config

from app.config import settings

_SESSION = aioboto3.Session(
    aws_access_key_id=settings.storage_access_key_id or None,
    aws_secret_access_key=settings.storage_secret_access_key or None,
    region_name=settings.storage_region,
)

_BOTO_CONFIG = Config(
    retries={"max_attempts": 3, "mode": "standard"},
    max_pool_connections=50,
)


def _storage_key(session_id: uuid.UUID, filename: str) -> str:
    """Deterministic storage path: raw/<session_id>/<filename>"""
    return f"raw/{session_id}/{filename}"


async def upload_file_stream(
    session_id: uuid.UUID,
    filename: str,
    data: AsyncIterator[bytes],
    content_type: str = "application/octet-stream",
) -> str:
    """
    Stream an async bytes iterator directly to object storage.
    Returns the storage key.
    """
    key = _storage_key(session_id, filename)
    endpoint = settings.storage_endpoint_url or None

    async with _SESSION.client(
        "s3",
        endpoint_url=endpoint,
        config=_BOTO_CONFIG,
    ) as s3:
        # Collect stream into a buffer for upload_fileobj
        # For files <= 500 MB this is acceptable; larger files would use multipart
        buf = io.BytesIO()
        async for chunk in data:
            buf.write(chunk)
        buf.seek(0)

        await s3.upload_fileobj(
            buf,
            settings.storage_bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )

    return key


async def upload_bytes(
    session_id: uuid.UUID,
    filename: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload bytes directly. Returns the storage key."""
    key = _storage_key(session_id, filename)
    endpoint = settings.storage_endpoint_url or None

    async with _SESSION.client(
        "s3",
        endpoint_url=endpoint,
        config=_BOTO_CONFIG,
    ) as s3:
        await s3.put_object(
            Bucket=settings.storage_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    return key


async def download_bytes(storage_key: str) -> bytes:
    """Download the full content of a stored file. Used by the processing worker."""
    endpoint = settings.storage_endpoint_url or None

    async with _SESSION.client(
        "s3",
        endpoint_url=endpoint,
        config=_BOTO_CONFIG,
    ) as s3:
        response = await s3.get_object(Bucket=settings.storage_bucket, Key=storage_key)
        return await response["Body"].read()
