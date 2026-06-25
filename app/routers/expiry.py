from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth import ADMIN_ROLES, require_user
from app.database import get_db
from app.services.expiry import expiry_summary
from app.templates import templates

router = APIRouter(prefix="/expiry")


@router.get("")
def expiry_dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db, ADMIN_ROLES)
    return templates.TemplateResponse(
        request,
        "expiry.html",
        {
            "request": request,
            "user": user,
            "expiry": expiry_summary(db),
        },
    )
