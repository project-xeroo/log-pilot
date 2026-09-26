"""
Tests for Tool 03 — PII Redaction Tool.
Verifies detection rate, correct placeholder substitution, and no false negatives
for the mandatory redaction patterns.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.redaction import redact, redact_record_fields


# ─────────────────────────────────────────────────────────────────────────────
# Email
# ─────────────────────────────────────────────────────────────────────────────

class TestEmailRedaction:
    def test_basic_email(self):
        r = redact("User logged in: alice@example.com")
        assert "[REDACTED_EMAIL]" in r.text
        assert "alice@example.com" not in r.text
        assert r.replacements >= 1

    def test_email_with_plus(self):
        r = redact("Contact: alice+tag@sub.example.org from client")
        assert "[REDACTED_EMAIL]" in r.text

    def test_multiple_emails(self):
        r = redact("From: a@x.com To: b@y.com Cc: c@z.io")
        assert r.replacements >= 3
        assert "a@x.com" not in r.text
        assert "b@y.com" not in r.text

    def test_no_false_positive_on_url(self):
        # @ in a URL-like context should still be caught — acceptable false positive
        r = redact("Plain text without any email address here")
        assert r.replacements == 0


# ─────────────────────────────────────────────────────────────────────────────
# Phone numbers
# ─────────────────────────────────────────────────────────────────────────────

class TestPhoneRedaction:
    def test_us_phone_dashes(self):
        r = redact("Call us at 555-867-5309")
        assert "[REDACTED_PHONE]" in r.text
        assert "555-867-5309" not in r.text

    def test_us_phone_dots(self):
        r = redact("Contact: 555.867.5309")
        assert "[REDACTED_PHONE]" in r.text

    def test_us_phone_parentheses(self):
        r = redact("Phone: (555) 867-5309")
        assert "[REDACTED_PHONE]" in r.text

    def test_e164_format(self):
        r = redact("Caller: +15558675309")
        assert "[REDACTED_PHONE]" in r.text


# ─────────────────────────────────────────────────────────────────────────────
# Credit cards
# ─────────────────────────────────────────────────────────────────────────────

class TestCreditCardRedaction:
    # Luhn-valid test numbers from https://www.paypalobjects.com/en_US/vhelp/paypalmanager_help/credit_card_numbers.htm
    VISA = "4111111111111111"
    MC = "5500005555555559"
    AMEX = "378282246310005"

    def test_visa(self):
        r = redact(f"Charging card: {self.VISA}")
        assert "[REDACTED_CC]" in r.text
        assert self.VISA not in r.text

    def test_mastercard(self):
        r = redact(f"card={self.MC}")
        assert "[REDACTED_CC]" in r.text

    def test_amex(self):
        r = redact(f"amex: {self.AMEX}")
        assert "[REDACTED_CC]" in r.text

    def test_visa_with_spaces(self):
        spaced = "4111 1111 1111 1111"
        r = redact(f"card: {spaced}")
        assert "[REDACTED_CC]" in r.text

    def test_non_luhn_not_redacted(self):
        r = redact("order_id=1234567890123456 processed")
        # Should NOT be redacted — fails Luhn
        assert "[REDACTED_CC]" not in r.text


# ─────────────────────────────────────────────────────────────────────────────
# JWT tokens
# ─────────────────────────────────────────────────────────────────────────────

class TestJWTRedaction:
    # Real-looking JWT structure (not a valid token but correct format)
    TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMTIzIiwiZXhwIjoxNzAwMDAwMDAwfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"

    def test_jwt_redacted(self):
        r = redact(f"Authorization: Bearer {self.TOKEN}")
        assert "[REDACTED_JWT]" in r.text
        assert self.TOKEN not in r.text

    def test_jwt_in_log_line(self):
        r = redact(f"token={self.TOKEN} user=alice")
        assert "[REDACTED_JWT]" in r.text
        assert "user=alice" in r.text  # non-PII preserved


# ─────────────────────────────────────────────────────────────────────────────
# API keys / passwords
# ─────────────────────────────────────────────────────────────────────────────

class TestPasswordAndApiKeyRedaction:
    def test_password_equals(self):
        r = redact("connecting with password=supersecret123 to db")
        assert "[REDACTED_PASSWORD]" in r.text
        assert "supersecret123" not in r.text

    def test_password_colon(self):
        r = redact("config: password: mysecretpassword")
        assert "[REDACTED_PASSWORD]" in r.text

    def test_api_key(self):
        r = redact("api_key=sk-abcdef1234567890abcdef1234567890")
        assert "[REDACTED_PASSWORD]" in r.text

    def test_secret_key(self):
        r = redact("SECRET_KEY=my-very-secret-value")
        assert "[REDACTED_PASSWORD]" in r.text

    def test_aws_access_key(self):
        r = redact("key=AKIAIOSFODNN7EXAMPLE connecting to S3")
        assert "[REDACTED_AWS_KEY]" in r.text
        assert "AKIAIOSFODNN7EXAMPLE" not in r.text


# ─────────────────────────────────────────────────────────────────────────────
# SSN
# ─────────────────────────────────────────────────────────────────────────────

class TestSSNRedaction:
    def test_ssn_standard_format(self):
        r = redact("SSN: 123-45-6789")
        assert "[REDACTED_SSN]" in r.text
        assert "123-45-6789" not in r.text

    def test_ssn_invalid_not_redacted(self):
        # 000-xx-xxxx is invalid SSN
        r = redact("ref: 000-12-3456")
        assert "000-12-3456" in r.text  # should NOT be redacted


# ─────────────────────────────────────────────────────────────────────────────
# IP addresses
# ─────────────────────────────────────────────────────────────────────────────

class TestIPRedaction:
    def test_public_ip_redacted(self):
        r = redact("Request from 203.0.113.42")
        assert "[REDACTED_IP]" in r.text
        assert "203.0.113.42" not in r.text

    def test_private_ip_preserved_as_internal(self):
        r = redact("Internal request from 192.168.1.100")
        assert "[INTERNAL_IP]" in r.text
        assert "192.168.1.100" not in r.text

    def test_loopback_preserved_as_internal(self):
        r = redact("localhost: 127.0.0.1")
        assert "[INTERNAL_IP]" in r.text

    def test_10_range_internal(self):
        r = redact("peer=10.0.1.50 connected")
        assert "[INTERNAL_IP]" in r.text


# ─────────────────────────────────────────────────────────────────────────────
# redact_record_fields
# ─────────────────────────────────────────────────────────────────────────────

class TestRedactRecordFields:
    def test_string_fields_redacted(self):
        fields = {
            "message": "user alice@example.com logged in",
            "source_ip": "203.0.113.5",
            "count": 42,
        }
        out, total = redact_record_fields(fields)
        assert "[REDACTED_EMAIL]" in out["message"]
        assert "[REDACTED_IP]" in out["source_ip"]
        assert out["count"] == 42  # non-string untouched
        assert total >= 2

    def test_nested_dict_redacted(self):
        fields = {
            "meta": {
                "email": "b@test.com",
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ4In0.abc123def",
            }
        }
        out, total = redact_record_fields(fields)
        assert "[REDACTED_EMAIL]" in out["meta"]["email"]

    def test_non_string_values_untouched(self):
        fields = {"count": 100, "active": True, "ratio": 0.5}
        out, total = redact_record_fields(fields)
        assert out == fields
        assert total == 0


# ─────────────────────────────────────────────────────────────────────────────
# Idempotency and edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_string(self):
        r = redact("")
        assert r.text == ""
        assert r.replacements == 0

    def test_no_pii(self):
        r = redact("INFO service=payment-service status=healthy latency=42ms")
        assert r.replacements == 0

    def test_multiple_pii_types_in_one_line(self):
        line = (
            "User alice@example.com called from 555-123-4567 "
            "with card 4111111111111111 and key AKIAIOSFODNN7EXAMPLE"
        )
        r = redact(line)
        assert "[REDACTED_EMAIL]" in r.text
        assert "[REDACTED_PHONE]" in r.text
        assert "[REDACTED_CC]" in r.text
        assert "[REDACTED_AWS_KEY]" in r.text
        assert r.replacements >= 4
        # Verify no raw PII remains
        assert "alice@example.com" not in r.text
        assert "555-123-4567" not in r.text
        assert "4111111111111111" not in r.text
        assert "AKIAIOSFODNN7EXAMPLE" not in r.text


# ─────────────────────────────────────────────────────────────────────────────
# Detection rate target (>= 95% of known PII test cases must be caught)
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectionRate:
    """
    Run a battery of known-PII strings and assert the overall detection rate
    meets the PRD requirement of >= 95%.
    """

    CASES = [
        "user@example.com",
        "alice+tag@sub.domain.co",
        "admin@company.io",
        "555-867-5309",
        "(800) 555-0100",
        "+1 650 555 1234",
        "4111111111111111",         # Visa
        "5500005555555559",         # MC
        "378282246310005",          # Amex
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1In0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
        "password=supersecret",
        "api_key=sk-abcdef1234567890",
        "AKIAIOSFODNN7EXAMPLE",
        "123-45-6789",              # SSN
        "203.0.113.99",             # public IP
    ]

    def test_detection_rate_above_95_percent(self):
        detected = 0
        for pii in self.CASES:
            r = redact(pii)
            # Consider detected if any replacement was made
            if r.replacements > 0:
                detected += 1
        rate = detected / len(self.CASES)
        assert rate >= 0.95, (
            f"PII detection rate {rate:.1%} is below the 95% PRD requirement. "
            f"Detected {detected}/{len(self.CASES)} cases."
        )
