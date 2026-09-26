"""
Tool 02 — Log Parsing Tool
Parsed record dataclass — intermediate representation before ORM model creation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ParsedRecord:
    """
    Intermediate representation of one parsed log line.
    All fields are optional — parsers set what they can detect.
    """
    raw_line: str = ""
    timestamp: datetime | None = None
    service_name: str | None = None
    severity: str = "UNKNOWN"
    message: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    environment: str | None = None
    deployment_version: str | None = None
    source_ip: str | None = None
    http_method: str | None = None
    http_path: str | None = None
    http_status: int | None = None
    duration_ms: float | None = None
    log_format: str = "unknown"
    extra_fields: dict[str, Any] = field(default_factory=dict)
    is_malformed: bool = False
