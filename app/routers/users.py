from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_permission, require_user
from app.database import get_db
from app.models import Batch, InventoryTransaction, Role, ScanLog, Serial, TallyMasterConfirmation, User, utc_now
from app.security import hash_password
from app.templates import templates

router = APIRouter(prefix="/users")


@router.get("")
def users_page(request: Request, error: str = "", db: Session = Depends(get_db)):
    user = require_permission(request, db, "users_manage")
    error_message = {
        "user_delete_self": "You cannot delete your own account",
    }.get(error, error)
    users = db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.username)).all()
    return templates.TemplateResponse(
        request,
        "users.html",
        {"request": request, "user": user, "users": users, "roles": list(Role), "error": error_message or None},
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
        users = db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.username)).all()
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
    if target and target.id != current.id and not target.deleted_at:
        target.active = not target.active
        db.commit()
    return RedirectResponse("/users", status_code=303)


@router.post("/{user_id}/delete")
def delete_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    current = require_user(request, db, {Role.SUPER_ADMIN})
    target = db.get(User, user_id)
    if not target:
        return RedirectResponse("/users", status_code=303)
    if target.id == current.id:
        return RedirectResponse("/users?error=user_delete_self", status_code=303)

    reference_count = sum(
        (
            db.scalar(select(func.count(Batch.id)).where(Batch.user_id == target.id)) or 0,
            db.scalar(select(func.count(InventoryTransaction.id)).where(InventoryTransaction.user_id == target.id)) or 0,
            db.scalar(select(func.count(ScanLog.id)).where(ScanLog.user_id == target.id)) or 0,
            db.scalar(select(func.count(Serial.id)).where(Serial.label_printed_by_id == target.id)) or 0,
            db.scalar(select(func.count(TallyMasterConfirmation.id)).where(TallyMasterConfirmation.confirmed_by_id == target.id)) or 0,
        )
    )
    if reference_count:
        target.active = False
        target.deleted_at = utc_now()
        db.commit()
        return RedirectResponse("/users", status_code=303)

    db.delete(target)
    db.commit()
    return RedirectResponse("/users", status_code=303)
