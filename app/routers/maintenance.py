from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import require_permission
from app.database import get_db
from app.services.backup import backup_status, create_sqlite_backup, sqlite_database_path
from app.templates import templates

router = APIRouter(prefix="/maintenance")


@router.get("")
def maintenance_page(request: Request, db: Session = Depends(get_db)):
    user = require_permission(request, db, "backup_data")
    return templates.TemplateResponse(
        request,
        "maintenance.html",
        {
            "request": request,
            "user": user,
            "database_path": sqlite_database_path(),
            "backup_status": backup_status(),
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
