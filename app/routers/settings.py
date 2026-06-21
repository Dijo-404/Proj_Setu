from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import ADMIN_ROLES, require_user
from app.database import get_db
from app.services.settings import DEFAULT_SETTINGS, get_all_settings, update_settings
from app.services.tally_masters import live_sync_readiness
from app.templates import templates

router = APIRouter(prefix="/settings")


@router.get("")
def settings_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db, ADMIN_ROLES)
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "user": user, "settings": get_all_settings(db), "keys": DEFAULT_SETTINGS.keys(), "error": None},
    )


@router.post("")
def save_settings(
    request: Request,
    company_name: str = Form(...),
    tally_enabled: str = Form("false"),
    tally_host: str = Form(...),
    tally_port: str = Form(...),
    sales_voucher_type: str = Form(...),
    purchase_voucher_type: str = Form(...),
    sales_ledger_name: str = Form(...),
    purchase_ledger_name: str = Form(...),
    cgst_ledger_name: str = Form(...),
    sgst_ledger_name: str = Form(...),
    round_off_ledger_name: str = Form(...),
    default_party_name: str = Form(...),
    retry_interval_seconds: str = Form(...),
    db: Session = Depends(get_db),
):
    require_user(request, db, ADMIN_ROLES)
    current_settings = get_all_settings(db)
    requested = {
        "company_name": company_name.strip(),
        "tally_enabled": "true" if tally_enabled == "true" else "false",
        "tally_host": tally_host.strip(),
        "tally_port": tally_port.strip(),
        "sales_voucher_type": sales_voucher_type.strip(),
        "purchase_voucher_type": purchase_voucher_type.strip(),
        "sales_ledger_name": sales_ledger_name.strip(),
        "purchase_ledger_name": purchase_ledger_name.strip(),
        "cgst_ledger_name": cgst_ledger_name.strip(),
        "sgst_ledger_name": sgst_ledger_name.strip(),
        "round_off_ledger_name": round_off_ledger_name.strip(),
        "default_party_name": default_party_name.strip(),
        "retry_interval_seconds": retry_interval_seconds.strip(),
    }
    if requested["tally_enabled"] == "true":
        update_settings(db, {key: value for key, value in requested.items() if key != "tally_enabled"})
        ready, counts = live_sync_readiness(db)
        if not ready:
            settings = get_all_settings(db)
            settings["tally_enabled"] = current_settings.get("tally_enabled", "false")
            return templates.TemplateResponse(
                "settings.html",
                {
                    "request": request,
                    "user": require_user(request, db, ADMIN_ROLES),
                    "settings": settings,
                    "keys": DEFAULT_SETTINGS.keys(),
                    "error": f"Complete Tally Check before enabling sync. Missing: {counts['missing']}, unchecked: {counts['unchecked']}.",
                },
                status_code=400,
            )
    update_settings(
        db,
        requested,
    )
    return RedirectResponse("/settings", status_code=303)
