"""
Operator CLI for the API Gateway.

Self-registration only allows developer / junior / viewer accounts, so the
first admin (and any SRE or manager) is created here:

    python -m app.cli create-user --email admin@example.com --role admin
    (password is prompted, or pass --password)
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import uuid

from sqlalchemy import text

from app.auth import hash_password
from shared.config import AsyncSessionLocal
from shared.models import Role


async def create_user(email: str, password: str, role: Role, full_name: str | None) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        existing = await db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email})
        if existing.first():
            raise SystemExit(f"A user with email {email!r} already exists.")
        user_id = uuid.uuid4()
        await db.execute(
            text("""
                INSERT INTO users (id, email, hashed_password, full_name, role)
                VALUES (:id, :email, :hashed_password, :full_name, CAST(:role AS userrole))
            """),
            {
                "id": user_id,
                "email": email,
                "hashed_password": hash_password(password),
                "full_name": full_name,
                "role": role.value,
            },
        )
        await db.commit()
        return user_id


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-user", help="Create a user with any role")
    create.add_argument("--email", required=True)
    create.add_argument("--role", required=True, choices=[r.value for r in Role])
    create.add_argument("--full-name")
    create.add_argument("--password", help="Prompted for if omitted")

    args = parser.parse_args(argv)
    password = args.password or getpass.getpass("Password: ")
    if len(password) < 8:
        sys.exit("Password must be at least 8 characters.")

    user_id = asyncio.run(create_user(args.email, password, Role(args.role), args.full_name))
    print(f"Created {args.role} user {args.email} ({user_id})")


if __name__ == "__main__":
    main()
