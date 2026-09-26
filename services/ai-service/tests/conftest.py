"""Ensure the ai-service app is on sys.path before any test module imports."""
import sys
import os

# Insert the service root so 'app' resolves to services/ai-service/app
_svc_root = os.path.dirname(os.path.dirname(__file__))
if _svc_root not in sys.path:
    sys.path.insert(0, _svc_root)
