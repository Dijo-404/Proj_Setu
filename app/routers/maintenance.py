from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import ADMIN_ROLES, require_user
from app.database import get_db
from app.services.backup import create_sqlite_backup, sqlite_database_path
from app.templates import templates

router = APIRouter(prefix="/maintenance")


@router.get("")
def maintenance_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db, ADMIN_ROLES)
    return templates.TemplateResponse(
        request,
        "maintenance.html",
        {"request": request, "user": user, "database_path": sqlite_database_path()},
    )


@router.get("/backup.db")
def download_backup(request: Request, db: Session = Depends(get_db)):
    require_user(request, db, ADMIN_ROLES)
    backup = create_sqlite_backup()
    return Response(
        backup.data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={backup.filename}"},
    )
