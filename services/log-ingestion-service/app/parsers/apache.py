"""
Tool 02 — Log Parsing Tool
Apache Common and Apache Combined log format parsers.

Apache Common Log Format:
  %h %l %u %t "%r" %>s %b
  127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /index.html HTTP/1.1" 200 2326

Apache Combined adds Referer and User-Agent fields after the status+bytes.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from app.parsers.models import ParsedRecord

# Compiled regex for Apache Common Log Format
_APACHE_COMMON_RE = re.compile(
    r'(?P<host>\S+)\s+'          # %h — client IP / hostname
    r'(?P<ident>\S+)\s+'         # %l — ident (usually -)
    r'(?P<user>\S+)\s+'          # %u — auth user (usually -)
    r'\[(?P<time>[^\]]+)\]\s+'   # %t — timestamp in brackets
    r'"(?P<request>[^"]+)"\s+'   # %r — request line in quotes
    r'(?P<status>\d{3})\s+'      # %>s — HTTP status code
    r'(?P<bytes>\S+)'            # %b — bytes sent (- if none)
)

# Apache Combined additionally captures referer and user-agent
_APACHE_COMBINED_RE = re.compile(
    _APACHE_COMMON_RE.pattern
    + r'\s+"(?P<referer>[^"]*)"\s+"(?P<useragent>[^"]*)"'
)

# Apache timestamp format
_APACHE_TS_FMT = "%d/%b/%Y:%H:%M:%S %z"


def _parse_apache_timestamp(ts_str: str) -> datetime | None:
    try:
        return datetime.strptime(ts_str, _APACHE_TS_FMT)
    except ValueError:
        return None


def _parse_request_line(request: str) -> tuple[str | None, str | None]:
    """Split 'METHOD /path HTTP/x.x' into (method, path)."""
    parts = request.split(" ", 2)
    if len(parts) >= 2:
        return parts[0].upper(), parts[1]
    return None, None


def try_parse_apache_combined(line: str) -> ParsedRecord | None:
    m = _APACHE_COMBINED_RE.match(line)
    if not m:
        return None
    record = _build_from_match(m, line)
    record.log_format = "apache_combined"
    record.extra_fields["referer"] = m.group("referer")
    record.extra_fields["user_agent"] = m.group("useragent")
    return record


def try_parse_apache_common(line: str) -> ParsedRecord | None:
    m = _APACHE_COMMON_RE.match(line)
    if not m:
        return None
    record = _build_from_match(m, line)
    record.log_format = "apache_common"
    return record


def _build_from_match(m: re.Match, raw_line: str) -> ParsedRecord:
    record = ParsedRecord(raw_line=raw_line)
    record.source_ip = m.group("host") if m.group("host") != "-" else None
    record.timestamp = _parse_apache_timestamp(m.group("time"))
    record.http_method, record.http_path = _parse_request_line(m.group("request"))
    try:
        record.http_status = int(m.group("status"))
    except (ValueError, TypeError):
        pass
    bytes_val = m.group("bytes")
    if bytes_val and bytes_val != "-":
        try:
            record.extra_fields["bytes_sent"] = int(bytes_val)
        except ValueError:
            pass
    # Derive severity from HTTP status
    status_code = record.http_status or 0
    if status_code >= 500:
        record.severity = "ERROR"
    elif status_code >= 400:
        record.severity = "WARN"
    else:
        record.severity = "INFO"
    return record
