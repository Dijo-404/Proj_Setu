from datetime import datetime, timedelta, timezone
from io import StringIO
import csv

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from app.auth import ADMIN_ROLES, require_user
from app.database import get_db
from app.models import Batch, ScanLog
from app.services.exports import scans_xlsx
from app.templates import templates

router = APIRouter(prefix="/reports")


def scan_query(action: str = "", start: str = "", end: str = ""):
    conditions = []
    if action:
        conditions.append(ScanLog.action == action)
    if start:
        start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
        conditions.append(ScanLog.created_at >= start_dt)
    if end:
        end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) + timedelta(days=1)
        conditions.append(ScanLog.created_at < end_dt)
    query = select(ScanLog).order_by(desc(ScanLog.created_at)).limit(500)
    if conditions:
        query = query.where(and_(*conditions))
    return query


@router.get("")
def reports(request: Request, action: str = "", start: str = "", end: str = "", db: Session = Depends(get_db)):
    user = require_user(request, db, ADMIN_ROLES)
    scans = db.scalars(scan_query(action, start, end)).all()
    pending = db.scalars(
        select(Batch)
        .where(Batch.status.in_(["PENDING_SYNC", "FAILED"]))
        .order_by(desc(Batch.created_at))
        .limit(50)
    ).all()
    return templates.TemplateResponse(
        request,
        "reports.html",
        {
            "request": request,
            "user": user,
            "scans": scans,
            "pending": pending,
            "action": action,
            "start": start,
            "end": end,
        },
    )


@router.get("/scans.csv")
def scans_csv(request: Request, action: str = "", start: str = "", end: str = "", db: Session = Depends(get_db)):
    require_user(request, db, ADMIN_ROLES)
    scans = db.scalars(scan_query(action, start, end)).all()
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(["Date", "User", "Action", "Serial", "Status", "Batch", "Message", "Tally Reference"])
    for scan in scans:
        writer.writerow(
            [
                scan.created_at.isoformat(),
                scan.user.username,
                scan.action,
                scan.serial_number_raw,
                scan.status,
                scan.batch.batch_number if scan.batch else "",
                scan.message or "",
                scan.tally_reference or "",
            ]
        )
    stream.seek(0)
    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=setu-scans.csv"},
    )


@router.get("/scans.xlsx")
def scans_excel(request: Request, action: str = "", start: str = "", end: str = "", db: Session = Depends(get_db)):
    require_user(request, db, ADMIN_ROLES)
    scans = db.scalars(scan_query(action, start, end)).all()
    return Response(
        scans_xlsx(scans),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=setu-scans.xlsx"},
    )
