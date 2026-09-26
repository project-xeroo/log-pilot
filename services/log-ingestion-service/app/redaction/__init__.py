"""
Tool 03 — PII Redaction Tool
==============================================
MANDATORY gate — runs before every storage write and before every AI model call.
Not configurable. Cannot be disabled or bypassed.

Detects and replaces:
  • Email addresses
  • Phone numbers (E.164 and common national formats)
  • Credit card numbers (Luhn-checkable 13–19 digit sequences)
  • JWT tokens (header.payload.signature)
  • API keys / Bearer tokens (high-entropy opaque strings)
  • Passwords in key=value / key: value patterns
  • IPv4 addresses (private ranges preserved as [INTERNAL_IP])
  • Social Security Numbers (US, NNN-NN-NNNN)
  • AWS access key IDs (AKIA…)

Each redacted span is replaced with a typed placeholder:
  [REDACTED_EMAIL], [REDACTED_PHONE], [REDACTED_CC],
  [REDACTED_JWT], [REDACTED_API_KEY], [REDACTED_PASSWORD],
  [REDACTED_IP], [REDACTED_SSN], [REDACTED_AWS_KEY]

Design principles:
  - Prefer false-positive redaction over false-negative leakage
  - Patterns are compiled once at module load
  - redact() is a pure function: stateless, thread-safe
  - Returns both the redacted text and a count of replacements made
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Email
_EMAIL = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# Phone numbers — E.164, US, international with country code
_PHONE = re.compile(
    r"(?<!\d)"
    r"(?:\+?1[-.\s]?)?"
    r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
    r"(?!\d)",
)

# Credit card — 13–19 digits, optional separators every 4
_CC = re.compile(
    r"(?<!\d)"
    r"(?:4[0-9]{12}(?:[0-9]{3,6})?|"           # Visa
    r"5[1-5][0-9]{14}|"                          # MC
    r"3[47][0-9]{13}|"                           # Amex
    r"3(?:0[0-5]|[68][0-9])[0-9]{11}|"          # Diners
    r"6(?:011|5[0-9]{2})[0-9]{12,15}|"          # Discover
    r"(?:[0-9]{4}[-\s]?){3}[0-9]{4,7})"         # Generic 16-digit with separators
    r"(?!\d)",
)

# JWT — three base64url segments separated by dots
_JWT = re.compile(
    r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+",
)

# Bearer / Authorization header tokens
_BEARER = re.compile(
    r"(?i)(?:bearer|token|auth(?:orization)?)\s+([A-Za-z0-9+/=_\-\.]{20,})",
)

# Password / secret in key=value or key: value form
# Matches both lowercase and uppercase, including ALL_CAPS env var style (SECRET_KEY=...)
_PASSWORD = re.compile(
    r"(?i)(?:password|passwd|pwd|secret(?:_?key)?|api_?key|access_?key|private_?key|credentials?|secret_?access)"
    r"\s*[:=]\s*"
    r"([\"']?)(\S+)\1",
)

# AWS Access Key ID
_AWS_KEY = re.compile(r"(?<![A-Z0-9])(AKIA[0-9A-Z]{16})(?![A-Z0-9])")

# Social Security Number (US)
_SSN = re.compile(r"(?<!\d)(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?!\d)")

# IPv4 — we redact public IPs; private ranges show as [INTERNAL_IP]
_IPV4 = re.compile(
    r"(?<!\d)"
    r"(?P<a>\d{1,3})\.(?P<b>\d{1,3})\.(?P<c>\d{1,3})\.(?P<d>\d{1,3})"
    r"(?!\d)"
)

_PRIVATE_RANGES = [
    (10, 0, 0, 0, 10, 255, 255, 255),
    (172, 16, 0, 0, 172, 31, 255, 255),
    (192, 168, 0, 0, 192, 168, 255, 255),
    (127, 0, 0, 0, 127, 255, 255, 255),
]


def _is_private_ip(a: int, b: int, c: int, d: int) -> bool:
    for r in _PRIVATE_RANGES:
        la, lb, lc, ld, ha, hb, hc, hd = r
        if (la <= a <= ha and lb <= b <= hb and lc <= c <= hc and ld <= d <= hd):
            return True
    return False


# ---------------------------------------------------------------------------
# Luhn check for credit cards (reduces false positives)
# ---------------------------------------------------------------------------

def _luhn_check(number: str) -> bool:
    digits = [int(c) for c in re.sub(r"[\s\-]", "", number) if c.isdigit()]
    if len(digits) < 13:
        return False
    total = 0
    odd = True
    for d in reversed(digits):
        if odd:
            total += d
        else:
            d *= 2
            total += d - 9 if d > 9 else d
        odd = not odd
    return total % 10 == 0


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class RedactionResult:
    text: str
    replacements: int = 0
    types_found: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core redaction function
# ---------------------------------------------------------------------------

def redact(text: str) -> RedactionResult:
    """
    Redact all PII from *text*.
    Returns a RedactionResult with the cleaned text and replacement counts.

    This is the ONLY entry point — callers must not bypass it.
    Runs in O(n) with respect to text length per pattern.
    """
    result = text
    replacements = 0
    types_found: list[str] = []

    def _sub(pattern: re.Pattern, replacement: str, check_fn=None) -> None:
        nonlocal result, replacements
        count = 0

        def _replace(m: re.Match) -> str:
            nonlocal count
            if check_fn and not check_fn(m.group(0)):
                return m.group(0)
            count += 1
            return replacement

        result = pattern.sub(_replace, result)
        if count:
            replacements += count
            types_found.append(replacement)

    # JWT first — catches tokens before the generic bearer pattern
    _sub(_JWT, "[REDACTED_JWT]")

    # Bearer / Authorization tokens
    def _bearer_replace(m: re.Match) -> str:
        nonlocal replacements
        replacements += 1
        types_found.append("[REDACTED_API_KEY]")
        return m.group(0).replace(m.group(1), "[REDACTED_API_KEY]")

    result = _BEARER.sub(_bearer_replace, result)

    # AWS access keys
    _sub(_AWS_KEY, "[REDACTED_AWS_KEY]")

    # Passwords / secrets (replace the value portion only)
    def _pwd_replace(m: re.Match) -> str:
        nonlocal replacements
        replacements += 1
        types_found.append("[REDACTED_PASSWORD]")
        # Keep the key name, replace the value
        full = m.group(0)
        val = m.group(2)
        return full.replace(val, "[REDACTED_PASSWORD]")

    result = _PASSWORD.sub(_pwd_replace, result)

    # Credit cards (only if Luhn-valid)
    _sub(_CC, "[REDACTED_CC]", check_fn=lambda v: _luhn_check(v))

    # SSN
    _sub(_SSN, "[REDACTED_SSN]")

    # Email
    _sub(_EMAIL, "[REDACTED_EMAIL]")

    # Phone
    _sub(_PHONE, "[REDACTED_PHONE]")

    # IPv4 — preserve private ranges
    def _ip_replace(m: re.Match) -> str:
        nonlocal replacements
        try:
            a, b, c, d = int(m.group("a")), int(m.group("b")), int(m.group("c")), int(m.group("d"))
        except ValueError:
            return m.group(0)
        if not all(0 <= x <= 255 for x in (a, b, c, d)):
            return m.group(0)
        if _is_private_ip(a, b, c, d):
            return "[INTERNAL_IP]"
        replacements += 1
        types_found.append("[REDACTED_IP]")
        return "[REDACTED_IP]"

    result = _IPV4.sub(_ip_replace, result)

    return RedactionResult(
        text=result,
        replacements=replacements,
        types_found=list(set(types_found)),
    )


def redact_record_fields(fields: dict) -> tuple[dict, int]:
    """
    Redact all string values in a dictionary of log record fields.
    Returns (redacted_dict, total_replacements).
    Used to redact extra_fields / parsed records before storage.
    """
    total = 0
    out = {}
    for k, v in fields.items():
        if isinstance(v, str):
            r = redact(v)
            out[k] = r.text
            total += r.replacements
        elif isinstance(v, dict):
            sub, sub_count = redact_record_fields(v)
            out[k] = sub
            total += sub_count
        else:
            out[k] = v
    return out, total
