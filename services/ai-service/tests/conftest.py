"""Ensure the ai-service app is on sys.path before any test module imports."""
import sys
import os

# Insert the service root so 'app' resolves to services/ai-service/app
_svc_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Always put this service first: every service has a top-level `app` package,
# and editable installs of other services may already be on sys.path.
if _svc_root in sys.path:
    sys.path.remove(_svc_root)
sys.path.insert(0, _svc_root)
for _name in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
    if not (getattr(sys.modules[_name], "__file__", "") or "").startswith(_svc_root):
        del sys.modules[_name]

# Provider tests mock the OpenAI HTTP API; a key must be present before
# app.config is first imported, otherwise the stub fallback is selected.
os.environ.setdefault("OPENAI_API_KEY", "test-key")
