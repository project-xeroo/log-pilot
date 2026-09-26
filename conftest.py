"""
Shared pytest configuration.
Adds the repo root and shared directory to sys.path so that
`from shared.models import ...` works in tests.

Individual service test directories have their own conftest.py that adds
the service root to sys.path so `from app.xxx import ...` resolves correctly.
"""

import sys
import os

_root = os.path.dirname(__file__)

# Root (for shared package)
sys.path.insert(0, _root)
# Add shared explicitly (some imports use `from shared.config import ...`)
sys.path.insert(0, os.path.join(_root, "shared"))
