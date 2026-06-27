from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_permission, require_user
from app.database import get_db
from app.models import Batch, InventoryTransaction, Role, ScanLog, Serial, TallyMasterConfirmation, User, utc_now
from app.security import MIN_PASSWORD_LENGTH, hash_password
from app.templates import templates

router = APIRouter(prefix="/users")


@router.get("")
def users_page(request: Request, error: str = "", success: str = "", db: Session = Depends(get_db)):
    user = require_permission(request, db, "users_manage")
    error_message = {
        "user_delete_self": "You cannot delete your own account",
        "password_reset_self": "Use Change password in your account menu to update your own password.",
        "password_too_short": f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        "password_mismatch": "Password and confirmation do not match.",
        "user_not_found": "User account was not found.",
    }.get(error, error)
    success_message = {
        "password_reset": "Password reset successfully.",
    }.get(success, success)
    users = db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.username)).all()
    return templates.TemplateResponse(
        request,
        "users.html",
        {
            "request": request,
            "user": user,
            "users": users,
            "roles": list(Role),
            "error": error_message or None,
            "success": success_message or None,
        },
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
            {
                "request": request,
                "user": user,
                "users": users,
                "roles": list(Role),
                "error": "Username already exists",
                "success": None,
            },
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


@router.post("/{user_id}/password")
def reset_user_password(
    request: Request,
    user_id: int,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    force_change: str | None = Form(None),
    db: Session = Depends(get_db),
):
    current = require_user(request, db, {Role.SUPER_ADMIN})
    target = db.get(User, user_id)
    if not target or target.deleted_at:
        return RedirectResponse("/users?error=user_not_found", status_code=303)
    if target.id == current.id:
        return RedirectResponse("/users?error=password_reset_self", status_code=303)
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return RedirectResponse("/users?error=password_too_short", status_code=303)
    if new_password != confirm_password:
        return RedirectResponse("/users?error=password_mismatch", status_code=303)

    target.password_hash = hash_password(new_password)
    target.must_change_password = force_change == "true"
    db.commit()
    return RedirectResponse("/users?success=password_reset", status_code=303)


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
