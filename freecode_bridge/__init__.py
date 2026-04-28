"""Python helpers for integrating the free-code CLI."""

from .free_code_cli_client import FreeCodeCliClient, extract_assistant_text
from .web_bridge import FreeCodeWebBridge, WebBridgeSession

__all__ = [
    "FreeCodeCliClient",
    "FreeCodeWebBridge",
    "WebBridgeSession",
    "extract_assistant_text",
]

try:
    from .api_server import create_app
except Exception:
    create_app = None
else:
    __all__.append("create_app")
