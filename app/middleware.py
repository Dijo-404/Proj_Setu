from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _host_only(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value if "//" in value else f"//{value}")
    return (parsed.hostname or "").lower() or None


class CSRFOriginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method not in SAFE_METHODS:
            source = request.headers.get("origin") or request.headers.get("referer")
            source_host = _host_only(source)
            if source_host is not None:
                expected = request.headers.get("x-forwarded-host") or request.headers.get("host")
                expected_host = _host_only(expected.split(",")[0] if expected else None)
                if expected_host is not None and source_host != expected_host:
                    return PlainTextResponse("CSRF origin check failed", status_code=403)
        return await call_next(request)
