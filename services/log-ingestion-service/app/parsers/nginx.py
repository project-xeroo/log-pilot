"""
Tool 02 — Log Parsing Tool — Nginx log parser.

Default Nginx combined log format:
  $remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent
  "$http_referer" "$http_user_agent" [$request_time]

The request_time field (in seconds, float) is optional — present in most
production configurations but absent from the default format.
"""
from __future__ import annotations

import re
from datetime import datetime

from app.parsers.models import ParsedRecord

# Nginx uses the same Common-style structure but its timestamp format differs
_NGINX_RE = re.compile(
    r'(?P<host>\S+)\s+'
    r'(?P<ident>\S+)\s+'
    r'(?P<user>\S+)\s+'
    r'\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<request>[^"]*)"\s+'
    r'(?P<status>\d{3})\s+'
    r'(?P<bytes>\S+)'
    r'(?:\s+"(?P<referer>[^"]*)"\s+"(?P<useragent>[^"]*)")?'
    r'(?:\s+\[?(?P<rt>[\d.]+)\]?)?'
)

# Nginx timestamp: 10/Oct/2000:13:55:36 +0000  (same as Apache)
_NGINX_TS_FMT = "%d/%b/%Y:%H:%M:%S %z"


def try_parse_nginx(line: str) -> ParsedRecord | None:
    m = _NGINX_RE.match(line)
    if not m:
        return None

    record = ParsedRecord(raw_line=line)
    record.log_format = "nginx"
    record.source_ip = m.group("host") if m.group("host") != "-" else None

    try:
        record.timestamp = datetime.strptime(m.group("time"), _NGINX_TS_FMT)
    except ValueError:
        pass

    request = m.group("request") or ""
    parts = request.split(" ", 2)
    if len(parts) >= 2:
        record.http_method = parts[0].upper()
        record.http_path = parts[1]

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

    if m.group("referer"):
        record.extra_fields["referer"] = m.group("referer")
    if m.group("useragent"):
        record.extra_fields["user_agent"] = m.group("useragent")
    if m.group("rt"):
        try:
            record.duration_ms = float(m.group("rt")) * 1000
        except ValueError:
            pass

    status_code = record.http_status or 0
    if status_code >= 500:
        record.severity = "ERROR"
    elif status_code >= 400:
        record.severity = "WARN"
    else:
        record.severity = "INFO"

    return record
