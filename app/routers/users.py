from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_permission
from app.database import get_db
from app.models import Role, User
from app.security import hash_password
from app.templates import templates

router = APIRouter(prefix="/users")


@router.get("")
def users_page(request: Request, db: Session = Depends(get_db)):
    user = require_permission(request, db, "users_manage")
    users = db.scalars(select(User).order_by(User.username)).all()
    return templates.TemplateResponse(
        request,
        "users.html",
        {"request": request, "user": user, "users": users, "roles": list(Role), "error": None},
    )


@router.post("")
def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_permission(request, db, "users_manage")
    db.add(User(username=username.strip().lower(), password_hash=hash_password(password), role=Role(role).value, active=True))
    try:
        db.commit()
    except Exception:
        db.rollback()
        users = db.scalars(select(User).order_by(User.username)).all()
        return templates.TemplateResponse(
            request,
            "users.html",
            {"request": request, "user": user, "users": users, "roles": list(Role), "error": "Username already exists"},
            status_code=400,
        )
    return RedirectResponse("/users", status_code=303)


@router.post("/{user_id}/toggle")
def toggle_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    current = require_permission(request, db, "users_manage")
    target = db.get(User, user_id)
    if target and target.id != current.id:
        target.active = not target.active
        db.commit()
    return RedirectResponse("/users", status_code=303)
