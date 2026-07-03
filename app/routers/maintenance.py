from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth import require_permission, require_user
from app.database import get_db
from app.models import LoginAudit, Role
from app.security import verify_password
from app.services.backup import backup_status, create_sqlite_backup, sqlite_database_path
from app.services.database_reset import reset_database_and_cache
from app.templates import templates

router = APIRouter(prefix="/maintenance")


@router.get("")
def maintenance_page(request: Request, error: str = "", success: str = "", db: Session = Depends(get_db)):
    user = require_permission(request, db, "backup_data")
    error_message = {
        "bad_password": "Password was incorrect. Database was not reset.",
        "confirm_required": "Type RESET to confirm the database reset.",
    }.get(error, error)
    success_message = {
        "database_reset": "Database and cache reset completed.",
    }.get(success, success)
    return templates.TemplateResponse(
        request,
        "maintenance.html",
        {
            "request": request,
            "user": user,
            "database_path": sqlite_database_path(),
            "backup_status": backup_status(),
            "error": error_message or None,
            "success": success_message or None,
        },
    )


@router.get("/backup.db")
def download_backup(request: Request, db: Session = Depends(get_db)):
    require_permission(request, db, "backup_download")
    backup = create_sqlite_backup()
    return Response(
        backup.data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={backup.filename}"},
    )


@router.post("/reset")
def reset_database(
    request: Request,
    super_admin_password: str = Form(...),
    confirm_reset: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_user(request, db, {Role.SUPER_ADMIN})
    if confirm_reset.strip() != "RESET":
        return RedirectResponse("/maintenance?error=confirm_required", status_code=303)
    if not verify_password(super_admin_password, user.password_hash):
        db.add(
            LoginAudit(
                username=user.username,
                success=False,
                ip_address=request.client.host if request.client else None,
                message="Database reset password verification failed",
            )
        )
        db.commit()
        return RedirectResponse("/maintenance?error=bad_password", status_code=303)

    reset_database_and_cache(db, user.id)
    return RedirectResponse("/maintenance?success=database_reset", status_code=303)
