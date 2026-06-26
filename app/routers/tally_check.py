from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_permission
from app.database import get_db
from app.services.settings import get_all_settings
from app.services.tally_masters import (
    collect_master_requirements,
    confirmation_lookup,
    confirm_master,
    readiness_counts,
    remove_confirmation,
    test_tally_gateway,
)
from app.templates import templates

router = APIRouter(prefix="/tally-check")


def render_check_page(request: Request, db: Session, result=None):
    user = require_permission(request, db, "tally_check_edit")
    requirements = collect_master_requirements(db)
    confirmations = confirmation_lookup(db)
    return templates.TemplateResponse(
        request,
        "tally_check.html",
        {
            "request": request,
            "user": user,
            "requirements": requirements,
            "confirmations": confirmations,
            "counts": readiness_counts(requirements, confirmations),
            "settings": get_all_settings(db),
            "result": result,
        },
    )


@router.get("")
def tally_check_page(request: Request, db: Session = Depends(get_db)):
    return render_check_page(request, db)


@router.post("/confirm")
def confirm(
    request: Request,
    master_type: str = Form(...),
    master_name: str = Form(...),
    source: str = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_permission(request, db, "tally_check_edit")
    confirm_master(db, user, master_type, master_name, source, notes)
    return RedirectResponse("/tally-check", status_code=303)


@router.post("/unconfirm")
def unconfirm(
    request: Request,
    master_type: str = Form(...),
    master_name: str = Form(...),
    db: Session = Depends(get_db),
):
    require_permission(request, db, "tally_check_edit")
    remove_confirmation(db, master_type, master_name)
    return RedirectResponse("/tally-check", status_code=303)


@router.post("/test-gateway")
def test_gateway(request: Request, db: Session = Depends(get_db)):
    require_permission(request, db, "tally_check_edit")
    result = test_tally_gateway(get_all_settings(db))
    return render_check_page(request, db, result)
