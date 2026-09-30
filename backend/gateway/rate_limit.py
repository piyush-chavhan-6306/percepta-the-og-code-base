"""
Border Intelligence Gateway Rate Limiting.
Provides token-bucket rate limiting via slowapi to prevent ingestion overload and API flooding.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from backend.config import get_settings

# Initialize Limiter keyed by client remote address
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{get_settings().RATE_LIMIT_PER_MINUTE}/minute"],
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Custom exception handler for rate-limit violations with security headers."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "Too Many Requests",
            "detail": f"Rate limit exceeded: {exc.detail}",
            "retry_after_seconds": 60,
        },
        headers={"Retry-After": "60"},
    )
