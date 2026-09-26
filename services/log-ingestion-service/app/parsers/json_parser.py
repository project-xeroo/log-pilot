"""
Tool 02 — Log Parsing Tool — JSON structured log parser.

Handles arbitrary JSON log lines. Extracts well-known fields
by trying a priority list of common key names per field.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .models import ParsedRecord

# Priority-ordered lists of JSON keys for each target field
_TIMESTAMP_KEYS = ["timestamp", "time", "ts", "@timestamp", "datetime", "date", "created_at"]
_SEVERITY_KEYS = ["level", "severity", "log_level", "loglevel", "lvl", "priority", "sev"]
_MESSAGE_KEYS = ["message", "msg", "text", "body", "log", "content"]
_SERVICE_KEYS = ["service", "service_name", "app", "application", "component", "logger"]
_REQUEST_ID_KEYS = ["request_id", "requestId", "req_id", "reqId", "correlation_id", "x-request-id"]
_TRACE_ID_KEYS = ["trace_id", "traceId", "trace", "dd.trace_id", "traceID"]
_ENV_KEYS = ["environment", "env", "stage", "deployment_env"]
_VERSION_KEYS = ["version", "app_version", "release", "deployment_version", "build"]

# Normalise severity strings to our enum values
_SEVERITY_NORM: dict[str, str] = {
    "trace": "TRACE",
    "debug": "DEBUG", "dbg": "DEBUG",
    "info": "INFO", "information": "INFO",
    "warn": "WARN", "warning": "WARN",
    "error": "ERROR", "err": "ERROR",
    "critical": "CRITICAL", "crit": "CRITICAL",
    "fatal": "FATAL",
}


def _extract(data: dict[str, Any], keys: list[str]) -> Any:
    """Return the first value found for any key in the priority list."""
    for k in keys:
        if k in data:
            return data[k]
    return None


def _parse_timestamp(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        # Unix epoch — determine seconds vs milliseconds
        if val > 1e12:
            val = val / 1000
        try:
            return datetime.fromtimestamp(val)
        except (ValueError, OSError):
            return None
    ts = str(val)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            pass
    return None


def _normalise_severity(val: Any) -> str:
    if val is None:
        return "UNKNOWN"
    return _SEVERITY_NORM.get(str(val).lower(), "UNKNOWN")


def try_parse_json(line: str) -> ParsedRecord | None:
    line = line.strip()
    if not (line.startswith("{") and line.endswith("}")):
        return None

    try:
        data: dict[str, Any] = json.loads(line)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    record = ParsedRecord(raw_line=line, log_format="json")

    record.timestamp = _parse_timestamp(_extract(data, _TIMESTAMP_KEYS))
    record.severity = _normalise_severity(_extract(data, _SEVERITY_KEYS))
    record.message = _extract(data, _MESSAGE_KEYS)
    record.service_name = _extract(data, _SERVICE_KEYS)
    record.request_id = _extract(data, _REQUEST_ID_KEYS)
    record.trace_id = _extract(data, _TRACE_ID_KEYS)
    record.environment = _extract(data, _ENV_KEYS)
    record.deployment_version = _extract(data, _VERSION_KEYS)

    # HTTP fields
    record.http_method = data.get("method") or data.get("http_method")
    record.http_path = data.get("path") or data.get("url") or data.get("uri")
    status = data.get("status") or data.get("status_code") or data.get("http_status")
    if status is not None:
        try:
            record.http_status = int(status)
        except (ValueError, TypeError):
            pass

    duration = data.get("duration") or data.get("duration_ms") or data.get("elapsed")
    if duration is not None:
        try:
            record.duration_ms = float(duration)
        except (ValueError, TypeError):
            pass

    # Preserve all remaining fields in extra_fields
    known = set(
        _TIMESTAMP_KEYS + _SEVERITY_KEYS + _MESSAGE_KEYS + _SERVICE_KEYS
        + _REQUEST_ID_KEYS + _TRACE_ID_KEYS + _ENV_KEYS + _VERSION_KEYS
        + ["method", "http_method", "path", "url", "uri",
           "status", "status_code", "http_status", "duration", "duration_ms", "elapsed"]
    )
    record.extra_fields = {k: v for k, v in data.items() if k not in known}

    return record
