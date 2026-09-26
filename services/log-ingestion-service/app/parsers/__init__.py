"""
Tool 02 — Log Parsing Tool — Auto-detection dispatcher.

Pipeline:
  1. Try JSON first (fastest, unambiguous)
  2. Try Apache Combined
  3. Try Apache Common
  4. Try Nginx
  5. Try RFC 5424 syslog
  6. Try RFC 3164 syslog
  7. Fall back to a generic timestamp+severity heuristic
  8. Return a raw record marked as "custom"

Also handles .gz and .zip decompression and .csv line splitting
before dispatching individual lines to the format parsers.
"""
from __future__ import annotations

import csv
import gzip
import io
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import structlog

from .models import ParsedRecord
from .apache import try_parse_apache_combined, try_parse_apache_common
from .nginx import try_parse_nginx
from .syslog import try_parse_rfc5424, try_parse_rfc3164
from .json_parser import try_parse_json

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Generic fallback — common "timestamp severity message" pattern
# Covers most application loggers: Log4j, Logback, Python logging, etc.
# ---------------------------------------------------------------------------

_GENERIC_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
    r"(?:\s+\[?(?P<level>TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\]?)?"
    r"(?:\s+\[?(?P<thread>[^\s\]]+)\]?)?"
    r"(?:\s+(?P<logger>[\w.$-]+(?:\.[\w.$-]+)+))?"
    r"\s*[-:–]?\s*(?P<message>.*)",
    re.IGNORECASE,
)

_SEVERITY_NORM = {
    "trace": "TRACE", "debug": "DEBUG", "info": "INFO",
    "warn": "WARN", "warning": "WARN", "error": "ERROR",
    "critical": "CRITICAL", "fatal": "FATAL",
}


def _try_generic(line: str) -> ParsedRecord | None:
    m = _GENERIC_RE.match(line)
    if not m or not m.group("ts"):
        return None

    record = ParsedRecord(raw_line=line, log_format="custom")
    ts_str = m.group("ts").replace(",", ".").replace(" ", "T")
    try:
        record.timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except ValueError:
        pass

    level = (m.group("level") or "").lower()
    record.severity = _SEVERITY_NORM.get(level, "UNKNOWN")
    record.message = (m.group("message") or "").strip()
    record.service_name = m.group("logger")
    return record


# ---------------------------------------------------------------------------
# Line-level dispatcher
# ---------------------------------------------------------------------------

def parse_line(line: str) -> ParsedRecord:
    """
    Auto-detect format and parse a single log line.
    Always returns a ParsedRecord — never raises.
    """
    line = line.rstrip("\n\r")
    if not line.strip():
        # Blank line — skip
        record = ParsedRecord(raw_line=line, is_malformed=False, severity="UNKNOWN")
        return record

    for parser in (
        try_parse_json,
        try_parse_apache_combined,
        try_parse_apache_common,
        try_parse_nginx,
        try_parse_rfc5424,
        try_parse_rfc3164,
        _try_generic,
    ):
        try:
            result = parser(line)
            if result is not None:
                return result
        except Exception as exc:
            log.warning("parser.exception", parser=parser.__name__, error=str(exc))

    # Absolute fallback — store raw line marked as custom/malformed
    return ParsedRecord(
        raw_line=line,
        message=line,
        log_format="custom",
        is_malformed=True,
        severity="UNKNOWN",
    )


# ---------------------------------------------------------------------------
# File-level iterator — handles compression and CSV
# ---------------------------------------------------------------------------

def iter_lines(content: bytes, filename: str) -> Iterator[str]:
    """
    Yield text lines from a raw bytes blob.
    Handles .gz, .zip, .csv, and plain text files.
    """
    ext = Path(filename).suffix.lower()

    if ext == ".gz":
        try:
            with gzip.open(io.BytesIO(content), "rt", encoding="utf-8", errors="replace") as f:
                yield from f
            return
        except (gzip.BadGzipFile, OSError):
            pass  # Fall through to plain-text treatment

    if ext == ".zip":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    with zf.open(name) as member:
                        text = member.read().decode("utf-8", errors="replace")
                        yield from text.splitlines()
            return
        except zipfile.BadZipFile:
            pass

    if ext == ".csv":
        text = content.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            # Yield each CSV row as a JSON line so the JSON parser handles it
            import json
            yield json.dumps(dict(row))
        return

    # Plain text (.log, .txt, .json, or fallback)
    text = content.decode("utf-8", errors="replace")
    yield from text.splitlines()


def parse_content(content: bytes, filename: str) -> tuple[list[ParsedRecord], str]:
    """
    Parse all lines from file content.
    Returns (records, detected_format_str).
    """
    records: list[ParsedRecord] = []
    format_votes: dict[str, int] = {}

    for line in iter_lines(content, filename):
        if not line.strip():
            continue
        record = parse_line(line)
        records.append(record)
        fmt = record.log_format
        format_votes[fmt] = format_votes.get(fmt, 0) + 1

    # Detect dominant format by vote
    dominant_format = max(format_votes, key=format_votes.get) if format_votes else "unknown"
    return records, dominant_format
