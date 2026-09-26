"""
Tool 01 — Log Ingestion Tool
Validates uploaded files: extension, size, and basic content-type checks.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.config import settings

# Maximum size enforced at the upload layer
_MAX_BYTES = settings.max_upload_size_bytes

# Allowed extensions (lowercase)
_ALLOWED_EXT = {ext.lower() for ext in settings.allowed_extensions}

# Magic bytes for supported compressed formats
_MAGIC_MAP: dict[bytes, str] = {
    b"\x1f\x8b": "gz",          # gzip
    b"PK\x03\x04": "zip",       # zip
}


def validate_upload(file: UploadFile) -> None:
    """
    Validate a file upload before accepting it.

    Raises HTTPException (422) on:
    - Unsupported file extension
    - File size exceeding 500 MB (checked against Content-Length when available)
    """
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()

    if ext not in _ALLOWED_EXT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported file type '{ext}'. "
                f"Allowed: {', '.join(sorted(_ALLOWED_EXT))}"
            ),
        )

    # Content-Length header check (fast path; full check happens on read)
    content_length = file.size  # UploadFile.size is set by FastAPI when available
    if content_length is not None and content_length > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the 500 MB upload limit ({content_length} bytes received).",
        )


def check_magic_bytes(header: bytes) -> str | None:
    """
    Return the detected format string if header matches a known magic signature,
    or None if no match is found (caller falls through to extension-based detection).
    """
    for magic, fmt in _MAGIC_MAP.items():
        if header[: len(magic)] == magic:
            return fmt
    return None
