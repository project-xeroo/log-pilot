"""
Shared pytest configuration.
Adds the repo root and each service directory to sys.path so that
`from services.forecasting_service.app.scoring import ...` works in tests.
"""

import sys
import os

_root = os.path.dirname(__file__)

# Add root + each service + shared to path
sys.path.insert(0, _root)
sys.path.insert(0, os.path.join(_root, "shared"))
for svc_dir in os.listdir(os.path.join(_root, "services")):
    sys.path.insert(0, os.path.join(_root, "services", svc_dir))
