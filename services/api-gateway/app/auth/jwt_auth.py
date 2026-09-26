"""
Compatibility aliases for routers written against the Phase 3/4 auth API.

All logic lives in ``app.auth``; these names map onto its permission model.
Use them with ``Depends(...)``.
"""

from __future__ import annotations

from app.auth import (  # noqa: F401 — re-exported
    TokenPayload,
    TokenResponse,
    create_access_token,
    decode_access_token,
    get_current_user,
    hash_password,
    require_roles,
    verify_password,
)
from shared.models import Role

# Any valid token, regardless of role
AnyAuthenticated = get_current_user
# Alert approval / analysis write actions (PRD §8.2)
SREOrAdmin = require_roles(Role.sre, Role.admin)
# Autonomy policy configuration
AdminOnly = require_roles(Role.admin)
