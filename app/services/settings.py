import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Company, Setting


COMPANY_SETTING_KEYS = [
    "company_name",
    "tally_host",
    "tally_port",
    "sales_voucher_type",
    "purchase_voucher_type",
    "sales_ledger_name",
    "purchase_ledger_name",
    "cgst_ledger_name",
    "sgst_ledger_name",
    "round_off_ledger_name",
    "default_party_name",
]


DEFAULT_SETTINGS = {
    "company_name": "",
    "tally_enabled": "false",
    "tally_host": "127.0.0.1",
    "tally_port": "9000",
    "sales_voucher_type": "",
    "purchase_voucher_type": "",
    "sales_ledger_name": "",
    "purchase_ledger_name": "",
    "cgst_ledger_name": "",
    "sgst_ledger_name": "",
    "round_off_ledger_name": "",
    "default_party_name": "",
    "retry_interval_seconds": "180",
    "movement_analysis_days": "90",
    "movement_dead_below_pct": "10",
    "movement_slow_below_pct": "40",
    "movement_medium_up_to_pct": "80",
}

LEGACY_PLACEHOLDER_SETTINGS = {
    "company_name": "SWARNAGOWRI",
    "tally_host": "127.0.0.1",
    "tally_port": "9000",
    "sales_voucher_type": "Sales",
    "purchase_voucher_type": "Purchase",
    "sales_ledger_name": "Sales @ 5%",
    "purchase_ledger_name": "Purchase @ 5%",
    "cgst_ledger_name": "Input CGST @  2.5 %",
    "sgst_ledger_name": "Input SGST@2.5%",
    "round_off_ledger_name": "ROUND OFF",
    "default_party_name": "Cash",
}


def ensure_default_settings(db: Session) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        if not db.get(Setting, key):
            db.add(Setting(key=key, value=value))
    db.commit()


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    if row:
        return row.value
    return DEFAULT_SETTINGS.get(key, default)


def get_all_settings(db: Session) -> dict[str, str]:
    values = DEFAULT_SETTINGS.copy()
    for row in db.query(Setting).all():
        values[row.key] = row.value
    return values


def update_settings(db: Session, values: dict[str, str]) -> None:
    for key, value in values.items():
        row = db.get(Setting, key)
        if row:
            row.value = value
        else:
            db.add(Setting(key=key, value=value))
    db.commit()


def clear_legacy_placeholder_settings(db: Session) -> None:
    if get_setting(db, "tally_enabled", "false").lower() == "true":
        return
    if any(get_setting(db, key, "") != value for key, value in LEGACY_PLACEHOLDER_SETTINGS.items()):
        return

    for key in COMPANY_SETTING_KEYS:
        row = db.get(Setting, key)
        if row:
            row.value = DEFAULT_SETTINGS[key]

    legacy_companies = db.scalars(select(Company).where(Company.name == LEGACY_PLACEHOLDER_SETTINGS["company_name"])).all()
    for company in legacy_companies:
        try:
            config = json.loads(company.config)
        except (TypeError, ValueError):
            config = {}
        if all(config.get(key) == LEGACY_PLACEHOLDER_SETTINGS[key] for key in COMPANY_SETTING_KEYS):
            db.delete(company)
    db.commit()


def is_tally_enabled(db: Session) -> bool:
    return get_setting(db, "tally_enabled", "false").lower() == "true"


def current_company_config(db: Session) -> dict[str, str]:
    return {key: get_setting(db, key) for key in COMPANY_SETTING_KEYS}


def list_companies(db: Session) -> list[Company]:
    return list(db.scalars(select(Company).order_by(Company.name)).all())


def get_active_company(db: Session) -> Company | None:
    return db.scalar(select(Company).where(Company.is_active.is_(True)))


def ensure_company_records(db: Session) -> None:
    if db.scalar(select(Company.id).limit(1)):
        if not get_active_company(db):
            first = db.scalar(select(Company).order_by(Company.id))
            first.is_active = True
            db.commit()
        return
    config = current_company_config(db)
    name = (config.get("company_name") or "").strip()
    if not name:
        return
    db.add(Company(name=name, config=json.dumps(config), is_active=True))
    db.commit()


def validate_company_fields(config: dict[str, str]) -> str | None:
    if not config.get("company_name", "").strip():
        return "Company name is required."
    if not config.get("tally_host", "").strip():
        return "Tally host is required."
    port = config.get("tally_port", "").strip()
    if not port.isdigit() or not (1 <= int(port) <= 65535):
        return "Tally port must be a whole number between 1 and 65535."
    return None


def add_company(db: Session, name: str, config: dict[str, str]) -> Company:
    clean = {key: (config.get(key, "") or "").strip() for key in COMPANY_SETTING_KEYS}
    label = (name or clean["company_name"]).strip()
    if not label:
        return _raise("A company label is required.")
    if db.scalar(select(Company).where(Company.name == label)):
        return _raise(f"A company named '{label}' already exists.")
    error = validate_company_fields(clean)
    if error:
        return _raise(error)
    is_first = db.scalar(select(Company.id).limit(1)) is None
    company = Company(name=label, config=json.dumps(clean), is_active=is_first)
    db.add(company)
    db.commit()
    if is_first:
        update_settings(db, clean)
    return company


def activate_company(db: Session, company_id: int) -> None:
    company = db.get(Company, company_id)
    if not company:
        return _raise("Company not found.")
    for other in list_companies(db):
        other.is_active = other.id == company.id
    db.commit()
    update_settings(db, {**json.loads(company.config), "tally_enabled": "false"})


def delete_company(db: Session, company_id: int) -> None:
    company = db.get(Company, company_id)
    if not company:
        return _raise("Company not found.")
    if (db.scalar(select(func.count(Company.id))) or 0) <= 1:
        return _raise("At least one company is required.")
    if company.is_active:
        return _raise("Activate another company before deleting this one.")
    db.delete(company)
    db.commit()


def save_active_company_config(db: Session, config: dict[str, str]) -> None:
    company = get_active_company(db)
    if not company:
        return
    clean = {key: (config.get(key, "") or "").strip() for key in COMPANY_SETTING_KEYS}
    company.config = json.dumps(clean)
    db.commit()


def _raise(message: str):
    raise ValueError(message)
