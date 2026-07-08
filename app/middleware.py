from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from app.auth import SESSION_COOKIE
from app.config import get_settings
from app.security import create_session_token

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
BACKGROUND_REQUEST_HEADER = "x-setuora-background"


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


class SessionActivityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        user_id = getattr(request.state, "session_user_id", None)
        if not user_id or request.headers.get(BACKGROUND_REQUEST_HEADER, "").lower() == "true":
            return response

        settings = get_settings()
        response.set_cookie(
            SESSION_COOKIE,
            create_session_token(user_id),
            max_age=settings.session_timeout_minutes * 60,
            httponly=True,
            samesite="lax",
            secure=settings.cookie_secure,
        )
        return response
