from collections import Counter
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.auth import require_permission
from app.database import get_db
from app.models import Batch, ScanLog
from app.services.charts import bar_chart, donut_chart
from app.services.expiry import expiry_summary
from app.services.inventory import dashboard_counts, status_summary
from app.templates import templates

router = APIRouter()


def _recent_batches(db: Session):
    return db.scalars(select(Batch).order_by(desc(Batch.created_at)).limit(8)).all()


def _recent_scans(db: Session):
    return db.scalars(select(ScanLog).order_by(desc(ScanLog.created_at)).limit(8)).all()


def _scan_activity_chart(db: Session):
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    start_at = datetime.combine(days[0], time.min, tzinfo=timezone.utc)
    timestamps = db.scalars(select(ScanLog.created_at).where(ScanLog.created_at >= start_at)).all()
    counts = Counter(timestamp.date() for timestamp in timestamps)
    return bar_chart(((day.strftime("%d %b"), counts[day]) for day in days), include_zero=True)


def _chart_context(db: Session):
    serial_status = status_summary(db)
    return {
        "status_summary": serial_status,
        "stock_chart": donut_chart(serial_status.items()),
        "scan_activity_chart": _scan_activity_chart(db),
    }


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_permission(request, db, "dashboard_data")
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "counts": dashboard_counts(db),
            **_chart_context(db),
            "expiry": expiry_summary(db),
            "recent_batches": _recent_batches(db),
            "recent_scans": _recent_scans(db),
        },
    )


@router.get("/dashboard/data")
def dashboard_data(request: Request, db: Session = Depends(get_db)):
    user = require_permission(request, db, "dashboard_data")
    batches_html = templates.env.get_template("partials/dashboard_batches.html").render(
        recent_batches=_recent_batches(db),
        user=user,
    )
    scans_html = templates.env.get_template("partials/dashboard_scans.html").render(
        recent_scans=_recent_scans(db)
    )
    charts_html = templates.env.get_template("partials/dashboard_charts.html").render(
        **_chart_context(db)
    )
    expiry_html = templates.env.get_template("partials/expiry_summary.html").render(
        expiry=expiry_summary(db),
        user=user,
    )
    return JSONResponse(
        {
            "counts": dashboard_counts(db),
            "charts_html": charts_html,
            "expiry_html": expiry_html,
            "batches_html": batches_html,
            "scans_html": scans_html,
        }
    )
