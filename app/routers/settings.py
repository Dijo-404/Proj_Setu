from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import ADMIN_ROLES, require_user
from app.database import get_db
from app.services.settings import (
    DEFAULT_SETTINGS,
    activate_company,
    add_company,
    delete_company,
    get_active_company,
    get_all_settings,
    list_companies,
    save_active_company_config,
    update_settings,
)
from app.services.tally_masters import live_sync_readiness
from app.templates import templates

router = APIRouter(prefix="/settings")


def validate_settings(requested: dict[str, str]) -> str | None:
    if not requested["company_name"]:
        return "Company name is required."
    if not requested["tally_host"]:
        return "Tally host is required."
    port = requested["tally_port"]
    if not port.isdigit() or not (1 <= int(port) <= 65535):
        return "Tally port must be a whole number between 1 and 65535."
    interval = requested["retry_interval_seconds"]
    if not interval.isdigit() or not (30 <= int(interval) <= 86400):
        return "Retry interval must be a whole number of seconds between 30 and 86400."
    return None


def render_settings(request: Request, db: Session, *, settings: dict | None = None, error: str | None = None, status_code: int = 200, open_settings: bool = False):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "request": request,
            "user": require_user(request, db, ADMIN_ROLES),
            "settings": settings if settings is not None else get_all_settings(db),
            "keys": DEFAULT_SETTINGS.keys(),
            "companies": list_companies(db),
            "active": get_active_company(db),
            "error": error,
            "open_settings": open_settings,
        },
        status_code=status_code,
    )


@router.get("")
def settings_page(request: Request, db: Session = Depends(get_db)):
    require_user(request, db, ADMIN_ROLES)
    return render_settings(request, db)


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

    validation_error = validate_settings(requested)
    if validation_error:
        settings = {**current_settings, **requested}
        settings["tally_enabled"] = current_settings.get("tally_enabled", "false")
        return render_settings(request, db, settings=settings, error=validation_error, status_code=400, open_settings=True)

    if requested["tally_enabled"] == "true":
        update_settings(db, {key: value for key, value in requested.items() if key != "tally_enabled"})
        save_active_company_config(db, requested)
        ready, counts = live_sync_readiness(db)
        if not ready:
            settings = get_all_settings(db)
            settings["tally_enabled"] = current_settings.get("tally_enabled", "false")
            return render_settings(
                request,
                db,
                settings=settings,
                error=f"Complete Tally Check before enabling sync. Missing: {counts['missing']}, unchecked: {counts['unchecked']}.",
                status_code=400,
                open_settings=True,
            )

    update_settings(db, requested)
    save_active_company_config(db, requested)
    return RedirectResponse("/settings", status_code=303)


@router.post("/autosave")
def autosave_settings(
    request: Request,
    company_name: str = Form(...),
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
    """Field-level auto-save for the active company. Never changes tally_enabled
    (enabling sync must go through the explicit Save button + readiness gate)."""
    require_user(request, db, ADMIN_ROLES)
    requested = {
        "company_name": company_name.strip(),
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
    error = validate_settings(requested)
    if error:
        return JSONResponse({"ok": False, "error": error}, status_code=400)
    update_settings(db, requested)
    save_active_company_config(db, requested)
    return JSONResponse({"ok": True})


@router.post("/companies")
def create_company(
    request: Request,
    name: str = Form(""),
    company_name: str = Form(...),
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
    db: Session = Depends(get_db),
):
    require_user(request, db, ADMIN_ROLES)
    config = {
        "company_name": company_name,
        "tally_host": tally_host,
        "tally_port": tally_port,
        "sales_voucher_type": sales_voucher_type,
        "purchase_voucher_type": purchase_voucher_type,
        "sales_ledger_name": sales_ledger_name,
        "purchase_ledger_name": purchase_ledger_name,
        "cgst_ledger_name": cgst_ledger_name,
        "sgst_ledger_name": sgst_ledger_name,
        "round_off_ledger_name": round_off_ledger_name,
        "default_party_name": default_party_name,
    }
    try:
        add_company(db, name, config)
    except ValueError as exc:
        return render_settings(request, db, error=str(exc), status_code=400)
    return RedirectResponse("/settings", status_code=303)


@router.post("/companies/{company_id}/activate")
def activate(request: Request, company_id: int, db: Session = Depends(get_db)):
    require_user(request, db, ADMIN_ROLES)
    try:
        activate_company(db, company_id)
    except ValueError as exc:
        return render_settings(request, db, error=str(exc), status_code=400)
    return RedirectResponse("/settings", status_code=303)


@router.post("/companies/{company_id}/delete")
def remove_company(request: Request, company_id: int, db: Session = Depends(get_db)):
    require_user(request, db, ADMIN_ROLES)
    try:
        delete_company(db, company_id)
    except ValueError as exc:
        return render_settings(request, db, error=str(exc), status_code=400)
    return RedirectResponse("/settings", status_code=303)
