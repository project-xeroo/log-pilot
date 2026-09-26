"""Ensure the forecasting-service app is on sys.path before any test module imports."""
import sys
import os

_svc_root = os.path.dirname(os.path.dirname(__file__))
if _svc_root not in sys.path:
    sys.path.insert(0, _svc_root)
