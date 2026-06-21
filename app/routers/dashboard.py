from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import Batch, ScanLog
from app.services.inventory import dashboard_counts, status_summary
from app.templates import templates

router = APIRouter()


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    recent_batches = db.scalars(select(Batch).order_by(desc(Batch.created_at)).limit(8)).all()
    recent_scans = db.scalars(select(ScanLog).order_by(desc(ScanLog.created_at)).limit(8)).all()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "counts": dashboard_counts(db),
            "status_summary": status_summary(db),
            "recent_batches": recent_batches,
            "recent_scans": recent_scans,
        },
    )
