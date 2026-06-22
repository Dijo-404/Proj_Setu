from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import SESSION_COOKIE, current_user, get_user_by_username
from app.database import get_db
from app.models import LoginAudit
from app.security import create_session_token, verify_password
from app.templates import templates

router = APIRouter()


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
    normalized = username.strip().lower()
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
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return redirect


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
