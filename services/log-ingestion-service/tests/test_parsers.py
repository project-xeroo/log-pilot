"""
Tests for Tool 02 — Log Parsing Tool.
Covers all five format parsers + the auto-detection dispatcher.
"""
from __future__ import annotations

import gzip
import io
import json
import zipfile

import pytest

# ---------------------------------------------------------------------------
# Parser imports (path assumes tests run from repo root)
# ---------------------------------------------------------------------------
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.parsers.apache import try_parse_apache_combined, try_parse_apache_common
from app.parsers.nginx import try_parse_nginx
from app.parsers.syslog import try_parse_rfc5424, try_parse_rfc3164
from app.parsers.json_parser import try_parse_json
from app.parsers import parse_line, iter_lines, parse_content


# ─────────────────────────────────────────────────────────────────────────────
# Apache Common
# ─────────────────────────────────────────────────────────────────────────────

class TestApacheCommon:
    LINE = '127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /index.html HTTP/1.1" 200 2326'

    def test_parses_ip(self):
        r = try_parse_apache_common(self.LINE)
        assert r is not None
        assert r.source_ip == "127.0.0.1"

    def test_parses_method_and_path(self):
        r = try_parse_apache_common(self.LINE)
        assert r.http_method == "GET"
        assert r.http_path == "/index.html"

    def test_parses_status(self):
        r = try_parse_apache_common(self.LINE)
        assert r.http_status == 200

    def test_severity_from_status_2xx(self):
        r = try_parse_apache_common(self.LINE)
        assert r.severity == "INFO"

    def test_severity_from_status_4xx(self):
        line = '127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET /nope HTTP/1.1" 404 512'
        r = try_parse_apache_common(line)
        assert r.severity == "WARN"

    def test_severity_from_status_5xx(self):
        line = '127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET /boom HTTP/1.1" 500 0'
        r = try_parse_apache_common(line)
        assert r.severity == "ERROR"

    def test_format_tag(self):
        r = try_parse_apache_common(self.LINE)
        assert r.log_format == "apache_common"

    def test_returns_none_on_non_apache(self):
        r = try_parse_apache_common('{"level": "info", "msg": "hello"}')
        assert r is None


class TestApacheCombined:
    LINE = (
        '192.168.1.1 - alice [01/Jan/2024:00:00:00 +0000] '
        '"POST /api/data HTTP/2.0" 201 1024 '
        '"https://example.com" "Mozilla/5.0"'
    )

    def test_parses_combined_fields(self):
        r = try_parse_apache_combined(self.LINE)
        assert r is not None
        assert r.http_method == "POST"
        assert r.http_path == "/api/data"
        assert r.extra_fields.get("referer") == "https://example.com"
        assert "Mozilla/5.0" in r.extra_fields.get("user_agent", "")

    def test_format_tag(self):
        r = try_parse_apache_combined(self.LINE)
        assert r.log_format == "apache_combined"


# ─────────────────────────────────────────────────────────────────────────────
# Nginx
# ─────────────────────────────────────────────────────────────────────────────

class TestNginx:
    LINE = (
        '10.0.0.5 - - [15/Mar/2024:09:30:00 +0000] '
        '"DELETE /resource/42 HTTP/1.1" 204 0 '
        '"-" "curl/7.68.0" [0.023]'
    )

    def test_parses_nginx_line(self):
        r = try_parse_nginx(self.LINE)
        assert r is not None
        assert r.http_method == "DELETE"
        assert r.http_path == "/resource/42"
        assert r.http_status == 204

    def test_duration_converted_to_ms(self):
        r = try_parse_nginx(self.LINE)
        assert r.duration_ms == pytest.approx(23.0, abs=0.1)

    def test_format_tag(self):
        r = try_parse_nginx(self.LINE)
        assert r.log_format == "nginx"

    def test_returns_none_on_json(self):
        assert try_parse_nginx('{"level":"info"}') is None


# ─────────────────────────────────────────────────────────────────────────────
# Syslog
# ─────────────────────────────────────────────────────────────────────────────

class TestSyslogRFC5424:
    LINE = (
        "<165>1 2024-01-15T10:30:00.000Z myhost.example.com myapp 12345 ID47 - "
        "An application event occurred"
    )

    def test_parses_timestamp(self):
        r = try_parse_rfc5424(self.LINE)
        assert r is not None
        assert r.timestamp is not None
        assert r.timestamp.year == 2024

    def test_parses_service_name(self):
        r = try_parse_rfc5424(self.LINE)
        assert r.service_name == "myapp"

    def test_parses_message(self):
        r = try_parse_rfc5424(self.LINE)
        assert "application event" in r.message

    def test_severity_from_pri(self):
        # PRI=165: facility=20 (local4), severity=5 (Notice -> INFO)
        r = try_parse_rfc5424(self.LINE)
        assert r.severity in ("INFO",)

    def test_format_tag(self):
        r = try_parse_rfc5424(self.LINE)
        assert r.log_format == "syslog"


class TestSyslogRFC3164:
    LINE = "Nov  3 10:22:39 myhost myapp[12345]: Connection refused to 10.0.0.1:5432"

    def test_parses_service_name(self):
        r = try_parse_rfc3164(self.LINE)
        assert r is not None
        assert r.service_name == "myapp"

    def test_parses_message(self):
        r = try_parse_rfc3164(self.LINE)
        assert "Connection refused" in r.message

    def test_parses_pid(self):
        r = try_parse_rfc3164(self.LINE)
        assert r.extra_fields.get("pid") == "12345"


# ─────────────────────────────────────────────────────────────────────────────
# JSON
# ─────────────────────────────────────────────────────────────────────────────

class TestJSONParser:
    def test_basic_json_log(self):
        line = json.dumps({
            "timestamp": "2024-01-15T10:30:00Z",
            "level": "ERROR",
            "message": "Database connection failed",
            "service": "payment-service",
            "trace_id": "abc-123",
        })
        r = try_parse_json(line)
        assert r is not None
        assert r.severity == "ERROR"
        assert r.message == "Database connection failed"
        assert r.service_name == "payment-service"
        assert r.trace_id == "abc-123"

    def test_unix_epoch_timestamp(self):
        line = json.dumps({"ts": 1705318200, "msg": "hello", "level": "info"})
        r = try_parse_json(line)
        assert r is not None
        assert r.timestamp is not None

    def test_unix_ms_timestamp(self):
        line = json.dumps({"ts": 1705318200000, "msg": "hello", "level": "debug"})
        r = try_parse_json(line)
        assert r is not None
        assert r.timestamp is not None

    def test_severity_normalisation(self):
        cases = [("warn", "WARN"), ("WARNING", "WARN"), ("fatal", "FATAL"), ("crit", "CRITICAL")]
        for raw, expected in cases:
            r = try_parse_json(json.dumps({"level": raw, "msg": "x"}))
            assert r.severity == expected, f"Expected {expected} for {raw}"

    def test_http_fields(self):
        line = json.dumps({
            "level": "info", "msg": "request",
            "method": "PUT", "path": "/items/5", "status": 200, "duration_ms": 45.2,
        })
        r = try_parse_json(line)
        assert r.http_method == "PUT"
        assert r.http_path == "/items/5"
        assert r.http_status == 200
        assert r.duration_ms == pytest.approx(45.2)

    def test_returns_none_on_non_json(self):
        assert try_parse_json("this is not json") is None

    def test_extra_fields_preserved(self):
        line = json.dumps({"level": "info", "msg": "hi", "my_custom_key": "my_value"})
        r = try_parse_json(line)
        assert r.extra_fields.get("my_custom_key") == "my_value"


# ─────────────────────────────────────────────────────────────────────────────
# Auto-detection dispatcher
# ─────────────────────────────────────────────────────────────────────────────

class TestParseLineDispatcher:
    def test_detects_json(self):
        r = parse_line('{"level": "info", "msg": "hello"}')
        assert r.log_format == "json"

    def test_detects_apache_combined(self):
        line = '1.2.3.4 - - [01/Jan/2024:00:00:00 +0000] "GET / HTTP/1.1" 200 1024 "-" "curl"'
        r = parse_line(line)
        assert r.log_format in ("apache_combined", "apache_common", "nginx")

    def test_detects_syslog_rfc5424(self):
        line = "<34>1 2024-01-15T10:30:00Z host app 1 - - message"
        r = parse_line(line)
        assert r.log_format == "syslog"

    def test_fallback_marks_malformed(self):
        r = parse_line("qwerty not a log line at all!!!")
        assert r.is_malformed is True

    def test_generic_log4j_style(self):
        line = "2024-01-15 10:30:00,123 ERROR [main] com.example.App - Something went wrong"
        r = parse_line(line)
        assert r.severity == "ERROR"
        assert r.timestamp is not None


# ─────────────────────────────────────────────────────────────────────────────
# File-level iter_lines
# ─────────────────────────────────────────────────────────────────────────────

class TestIterLines:
    def test_plain_text(self):
        content = b"line one\nline two\nline three\n"
        lines = list(iter_lines(content, "test.log"))
        assert lines == ["line one", "line two", "line three"]

    def test_gzip(self):
        raw = b"line one\nline two\n"
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(raw)
        lines = [l.rstrip("\n\r") for l in iter_lines(buf.getvalue(), "test.log.gz")]
        assert "line one" in lines
        assert "line two" in lines

    def test_zip(self):
        raw = b"line alpha\nline beta\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("logs.log", raw.decode())
        lines = list(iter_lines(buf.getvalue(), "archive.zip"))
        assert "line alpha" in lines

    def test_csv(self):
        csv_content = b"level,message\nINFO,hello world\nERROR,something broke\n"
        lines = list(iter_lines(csv_content, "logs.csv"))
        # CSV lines are emitted as JSON objects
        parsed = [json.loads(l) for l in lines]
        assert parsed[0]["level"] == "INFO"
        assert parsed[1]["message"] == "something broke"


# ─────────────────────────────────────────────────────────────────────────────
# parse_content — dominant format detection
# ─────────────────────────────────────────────────────────────────────────────

class TestParseContent:
    def test_json_file_detected(self):
        lines = [
            json.dumps({"level": "info", "msg": f"record {i}"})
            for i in range(10)
        ]
        content = "\n".join(lines).encode()
        records, fmt = parse_content(content, "app.log")
        assert fmt == "json"
        assert len(records) == 10

    def test_apache_file_detected(self):
        lines = [
            f'1.2.3.{i} - - [01/Jan/2024:00:00:00 +0000] "GET /{i} HTTP/1.1" 200 100 "-" "curl"'
            for i in range(5)
        ]
        content = "\n".join(lines).encode()
        records, fmt = parse_content(content, "access.log")
        assert fmt in ("apache_combined", "nginx")
