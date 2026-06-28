from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_permission
from app.database import get_db
from app.models import Company
from app.services.access_control import role_has_access
from app.services.change_audit import record_change
from app.services.settings import (
    company_config,
    get_active_company,
    get_all_settings,
    list_companies,
    update_company,
)
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


def company_snapshot(company: Company | None) -> dict[str, object] | None:
    if not company:
        return None
    return {
        "id": company.id,
        "name": company.name,
        "is_active": company.is_active,
        "config": company_config(company),
    }


def render_check_page(
    request: Request,
    db: Session,
    result=None,
    open_company_id: int | None = None,
):
    user = require_permission(request, db, "tally_check_edit")
    requirements = collect_master_requirements(db)
    confirmations = confirmation_lookup(db)
    companies = list_companies(db)
    active = get_active_company(db)
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
            "companies": [
                {"company": company, "config": company_config(company)}
                for company in companies
            ],
            "active": active,
            "can_edit_companies": role_has_access(db, user.role, "settings_edit"),
            "open_company_id": (
                open_company_id
                or (active.id if result is not None and active is not None else None)
            ),
        },
    )


@router.get("")
def tally_check_page(
    request: Request,
    company: int | None = None,
    db: Session = Depends(get_db),
):
    return render_check_page(request, db, open_company_id=company)


@router.post("/companies/{company_id}")
def save_company(
    request: Request,
    company_id: int,
    name: str = Form(...),
    company_name: str = Form(...),
    tally_host: str = Form(...),
    tally_port: str = Form(...),
    sales_voucher_type: str = Form(...),
    purchase_voucher_type: str = Form(...),
    sales_ledger_name: str = Form(...),
    purchase_ledger_name: str = Form(...),
    cgst_ledger_name: str = Form(...),
    sgst_ledger_name: str = Form(...),
    sales_gst_ledger_mappings: str = Form(""),
    round_off_ledger_name: str = Form(...),
    default_party_name: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_permission(request, db, "settings_edit")
    before = company_snapshot(db.get(Company, company_id))
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
        "sales_gst_ledger_mappings": sales_gst_ledger_mappings,
        "round_off_ledger_name": round_off_ledger_name,
        "default_party_name": default_party_name,
    }
    try:
        company = update_company(db, company_id, name, config, commit=False)
        record_change(
            db,
            user,
            entity_type="company",
            entity_id=company.id,
            action="update",
            before=before,
            after=company_snapshot(company),
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception:
        db.rollback()
        raise
    return JSONResponse(
        {
            "ok": True,
            "company": {
                "id": company.id,
                "name": company.name,
                "tally_company_name": company.tally_company_name,
            },
        }
    )


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
    active = get_active_company(db)
    target = f"/tally-check?company={active.id}" if active else "/tally-check"
    return RedirectResponse(target, status_code=303)


@router.post("/unconfirm")
def unconfirm(
    request: Request,
    master_type: str = Form(...),
    master_name: str = Form(...),
    db: Session = Depends(get_db),
):
    require_permission(request, db, "tally_check_edit")
    remove_confirmation(db, master_type, master_name)
    active = get_active_company(db)
    target = f"/tally-check?company={active.id}" if active else "/tally-check"
    return RedirectResponse(target, status_code=303)


@router.post("/test-gateway")
def test_gateway(request: Request, db: Session = Depends(get_db)):
    require_permission(request, db, "tally_check_edit")
    result = test_tally_gateway(get_all_settings(db))
    active = get_active_company(db)
    return render_check_page(
        request,
        db,
        result,
        open_company_id=active.id if active else None,
    )
