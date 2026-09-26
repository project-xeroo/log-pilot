"""
Tool 02 — Log Parsing Tool — Syslog parser.

Handles RFC 3164 and RFC 5424 syslog formats, plus the common
systemd journal "priority: message" shorthand.

RFC 3164: <PRI>Mon DD HH:MM:SS hostname app[pid]: message
RFC 5424: <PRI>VERSION TIMESTAMP HOSTNAME APP-NAME PROCID MSGID SD MSG
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .models import ParsedRecord

# RFC 3164 — the classic BSD syslog format
# <165>Nov  3 10:22:39 myhost myapp[12345]: This is the message
_RFC3164_RE = re.compile(
    r"(?:<\d+>)?"                               # optional PRI
    r"(?P<month>\w{3})\s+(?P<day>\d{1,2})\s+(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+"
    r"(?P<app>[^\[:]+?)(?:\[(?P<pid>\d+)\])?:\s*"
    r"(?P<message>.*)"
)

# RFC 5424
# <165>1 2003-10-11T22:14:15.003Z mymachine.example.com evntslog - ID47 [...] msg
_RFC5424_RE = re.compile(
    r"<(?P<pri>\d+)>(?P<version>\d+)\s+"
    r"(?P<ts>\S+)\s+"
    r"(?P<host>\S+)\s+"
    r"(?P<app>\S+)\s+"
    r"(?P<proc>\S+)\s+"
    r"(?P<msgid>\S+)\s+"
    r"(?:(?P<sd>\[.*?\](?:\s*\[.*?\])*|-)\s+)?"
    r"(?P<message>.*)"
)

_SEVERITY_MAP = {
    0: "CRITICAL",  # Emergency
    1: "CRITICAL",  # Alert
    2: "CRITICAL",  # Critical
    3: "ERROR",     # Error
    4: "WARN",      # Warning
    5: "INFO",      # Notice
    6: "INFO",      # Informational
    7: "DEBUG",     # Debug
}

_MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _pri_to_severity(pri: int) -> str:
    severity_int = pri % 8
    return _SEVERITY_MAP.get(severity_int, "UNKNOWN")


def try_parse_rfc5424(line: str) -> ParsedRecord | None:
    m = _RFC5424_RE.match(line)
    if not m:
        return None

    record = ParsedRecord(raw_line=line, log_format="syslog")

    try:
        record.severity = _pri_to_severity(int(m.group("pri")))
    except (ValueError, TypeError):
        pass

    ts_str = m.group("ts")
    if ts_str and ts_str != "-":
        try:
            record.timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            pass

    host = m.group("host")
    record.source_ip = host if host and host != "-" else None

    app = m.group("app")
    record.service_name = app if app and app != "-" else None

    msgid = m.group("msgid")
    if msgid and msgid != "-":
        record.request_id = msgid

    record.message = m.group("message") or ""
    record.extra_fields["pid"] = m.group("proc")
    return record


def try_parse_rfc3164(line: str) -> ParsedRecord | None:
    m = _RFC3164_RE.match(line)
    if not m:
        return None

    record = ParsedRecord(raw_line=line, log_format="syslog")

    month = _MONTH_MAP.get(m.group("month"), 1)
    day = int(m.group("day"))
    time_str = m.group("time")
    try:
        now = datetime.now(tz=timezone.utc)
        record.timestamp = datetime(
            year=now.year, month=month, day=day,
            hour=int(time_str[:2]), minute=int(time_str[3:5]), second=int(time_str[6:]),
            tzinfo=timezone.utc,
        )
    except (ValueError, IndexError):
        pass

    record.source_ip = m.group("host")
    record.service_name = m.group("app").strip() if m.group("app") else None
    record.message = m.group("message") or ""
    if m.group("pid"):
        record.extra_fields["pid"] = m.group("pid")

    # RFC 3164 has no built-in severity in the text portion — default INFO
    record.severity = "INFO"
    return record
