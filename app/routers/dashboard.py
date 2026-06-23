from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import Batch, ScanLog
from app.services.inventory import dashboard_counts, status_summary
from app.templates import templates

router = APIRouter()


def _recent_batches(db: Session):
    return db.scalars(select(Batch).order_by(desc(Batch.created_at)).limit(8)).all()


def _recent_scans(db: Session):
    return db.scalars(select(ScanLog).order_by(desc(ScanLog.created_at)).limit(8)).all()


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "counts": dashboard_counts(db),
            "status_summary": status_summary(db),
            "recent_batches": _recent_batches(db),
            "recent_scans": _recent_scans(db),
        },
    )


@router.get("/dashboard/data")
def dashboard_data(request: Request, db: Session = Depends(get_db)):
    """Live data for the dashboard poller (live.js). Renders the same row
    partials the page uses, so markup stays single-sourced."""
    require_user(request, db)
    batches_html = templates.env.get_template("partials/dashboard_batches.html").render(
        recent_batches=_recent_batches(db)
    )
    scans_html = templates.env.get_template("partials/dashboard_scans.html").render(
        recent_scans=_recent_scans(db)
    )
    return JSONResponse(
        {
            "counts": dashboard_counts(db),
            "batches_html": batches_html,
            "scans_html": scans_html,
        }
    )
