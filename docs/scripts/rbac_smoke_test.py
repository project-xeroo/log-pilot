#!/usr/bin/env python3
"""RBAC smoke test — verifies all four roles are enforced across API endpoints.

Usage:
    python docs/scripts/rbac_smoke_test.py [--base-url http://localhost:8000]

The script registers one test user per role, exercises every endpoint, and
prints a pass/fail table.  Exits 1 if any RBAC check fails.
"""
from __future__ import annotations

import argparse
import sys
import uuid
import requests

ROLES = ["admin", "sre", "developer", "viewer"]

ENDPOINT_MATRIX = [
    # (method, path_template, expected_status_by_role)
    # expected_status: dict[role, int]  — if None, any 2xx passes
    ("GET",    "/reports",               {"admin": 200, "sre": 200, "developer": 200, "viewer": 200}),
    ("POST",   "/reports/generate",      {"admin": 202, "sre": 202, "developer": 403, "viewer": 403}),
    ("GET",    "/outcomes",              {"admin": 200, "sre": 200, "developer": 200, "viewer": 200}),
    ("POST",   "/outcomes",              {"admin": 201, "sre": 201, "developer": 403, "viewer": 403}),
    ("GET",    "/deployments",           {"admin": 200, "sre": 200, "developer": 200, "viewer": 200}),
    ("GET",    "/deployments/compare",   {"admin": 422, "sre": 422, "developer": 422, "viewer": 403}),  # 422 = missing params
    ("GET",    "/users",                 {"admin": 200, "sre": 403, "developer": 403, "viewer": 403}),
]

GENERATE_BODY = {
    "incident_id": "SMOKE-001",
    "title": "RBAC smoke test incident",
    "severity": "low",
}


def register(base: str, role: str) -> str:
    """Register a test user and return a JWT token."""
    suffix = uuid.uuid4().hex[:8]
    r = requests.post(
        f"{base}/auth/register",
        json={
            "email": f"smoke-{role}-{suffix}@test.invalid",
            "password": "Smoke123!",
            "full_name": f"Smoke {role.title()}",
            "role": role,
        },
    )
    r.raise_for_status()
    return r.json()["access_token"]


def check(base: str, method: str, path: str, token: str, body: dict | None = None) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    kwargs: dict = {"headers": headers, "timeout": 10}
    if body:
        kwargs["json"] = body
    fn = getattr(requests, method.lower())
    r = fn(f"{base}{path}", **kwargs)
    return r.status_code


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    print(f"\n{'─' * 70}")
    print(f"  LogPilot RBAC Smoke Test  →  {base}")
    print(f"{'─' * 70}")

    # Register one token per role
    tokens: dict[str, str] = {}
    for role in ROLES:
        try:
            tokens[role] = register(base, role)
            print(f"  [✓] Registered {role}")
        except Exception as e:
            print(f"  [✗] Failed to register {role}: {e}")
            sys.exit(1)

    failures = 0
    print()
    header = f"{'Endpoint':<42}" + "".join(f"{r:>12}" for r in ROLES)
    print(header)
    print("─" * len(header))

    for method, path, expected in ENDPOINT_MATRIX:
        body = GENERATE_BODY if path == "/reports/generate" else None
        row = f"{method} {path}"[:41].ljust(42)
        for role in ROLES:
            actual = check(base, method, path, tokens[role], body)
            want = expected.get(role)
            ok = (want is None and 200 <= actual < 300) or actual == want
            mark = "✓" if ok else f"✗({actual}≠{want})"
            row += f"{mark:>12}"
            if not ok:
                failures += 1
        print(row)

    print()
    if failures:
        print(f"  ✗ {failures} RBAC check(s) FAILED")
        sys.exit(1)
    else:
        print("  ✓ All RBAC checks passed")


if __name__ == "__main__":
    main()
