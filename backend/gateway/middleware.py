"""
Border Intelligence Gateway Middleware.
Provides security headers, request telemetry logging, and prominent demo mode startup notices.
"""
import logging
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.config import get_settings

logger = logging.getLogger("border_gateway")


class GatewaySecurityMiddleware(BaseHTTPMiddleware):
    """Adds security headers, request timing metrics, and operational audit telemetry."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()

        response: Response = await call_next(request)

        process_time_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.2f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        return response


def log_gateway_startup_banner() -> None:
    """Emits informative console banner regarding active gateway mode."""
    settings = get_settings()
    if settings.DEMO_MODE:
        print("\n" + "=" * 68)
        print("  [PERCEPTA API GATEWAY]  --  DEMO_MODE IS ACTIVE")
        print("  Authentication is currently optional for seamless evaluation.")
        print("  JWT Token Authentication and RBAC endpoints remain functional.")
        print("=" * 68 + "\n")
    else:
        print("\n" + "=" * 68)
        print("  [PERCEPTA API GATEWAY]  --  STRICT AUTH ACTIVE")
        print("  All requests must supply 'Authorization: Bearer <token>'")
        print("=" * 68 + "\n")
