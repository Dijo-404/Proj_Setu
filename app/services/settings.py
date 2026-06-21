from sqlalchemy.orm import Session

from app.models import Setting


DEFAULT_SETTINGS = {
    "company_name": "SWARNAGOWRI",
    "tally_enabled": "false",
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
    "retry_interval_seconds": "180",
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


def is_tally_enabled(db: Session) -> bool:
    return get_setting(db, "tally_enabled", "false").lower() == "true"
