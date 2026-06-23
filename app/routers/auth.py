from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import SESSION_COOKIE, current_user, get_user_by_username
from app.config import get_settings
from app.database import get_db
from app.models import LoginAudit
from app.security import create_session_token, verify_password
from app.templates import templates

router = APIRouter()


def recent_failed_logins(db: Session, username: str, window_minutes: int) -> int:
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    return db.scalar(
        select(func.count(LoginAudit.id)).where(
            LoginAudit.username == username,
            LoginAudit.success.is_(False),
            LoginAudit.created_at >= since,
        )
    ) or 0


@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    if current_user(request, db):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": None})


@router.post("/login")
def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    normalized = username.strip().lower()

    if recent_failed_logins(db, normalized, settings.login_lockout_minutes) >= settings.login_max_attempts:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "request": request,
                "error": f"Too many failed attempts. Try again in about {settings.login_lockout_minutes} minutes.",
            },
            status_code=429,
        )

    user = get_user_by_username(db, normalized)
    ok = bool(user and user.active and verify_password(password, user.password_hash))
    db.add(
        LoginAudit(
            username=normalized,
            success=ok,
            ip_address=request.client.host if request.client else None,
            message="OK" if ok else "Invalid username or password",
        )
    )
    if not ok:
        db.commit()
        return templates.TemplateResponse(
            request,
            "login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=400,
        )
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    redirect = RedirectResponse("/", status_code=303)
    redirect.set_cookie(
        SESSION_COOKIE,
        create_session_token(user.id),
        max_age=settings.session_timeout_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return redirect


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
