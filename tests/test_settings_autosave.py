import inspect
import json

from app.routers.settings import autosave_settings, validate_settings
from app.services.settings import (
    COMPANY_SETTING_KEYS,
    ensure_company_records,
    ensure_default_settings,
    get_active_company,
    get_all_settings,
    save_active_company_config,
    update_settings,
)


def _seed(db):
    ensure_default_settings(db)
    ensure_company_records(db)


def _valid_request(db):
    settings = get_all_settings(db)
    requested = {key: settings[key] for key in COMPANY_SETTING_KEYS}
    requested["retry_interval_seconds"] = settings["retry_interval_seconds"]
    return requested


def test_autosave_endpoint_cannot_change_tally_enabled():
    # Structural guard: the auto-save route must not accept tally_enabled,
    # so field edits can never silently enable Tally sync (readiness gate stays
    # behind the explicit Save button).
    params = inspect.signature(autosave_settings).parameters
    assert "tally_enabled" not in params


def test_autosave_persists_fields_and_mirrors_active_company(db_session):
    _seed(db_session)
    assert get_all_settings(db_session)["tally_enabled"] == "false"

    requested = _valid_request(db_session)
    requested["sales_ledger_name"] = "Sales @ 12%"
    requested["retry_interval_seconds"] = "200"
    assert validate_settings(requested) is None

    update_settings(db_session, requested)
    save_active_company_config(db_session, requested)

    saved = get_all_settings(db_session)
    assert saved["sales_ledger_name"] == "Sales @ 12%"
    assert saved["retry_interval_seconds"] == "200"
    assert saved["tally_enabled"] == "false"  # untouched

    active = get_active_company(db_session)
    assert json.loads(active.config)["sales_ledger_name"] == "Sales @ 12%"


def test_autosave_validation_rejects_bad_port_and_interval(db_session):
    _seed(db_session)
    bad_port = _valid_request(db_session)
    bad_port["tally_port"] = "99999"
    assert validate_settings(bad_port) is not None

    bad_interval = _valid_request(db_session)
    bad_interval["retry_interval_seconds"] = "5"
    assert validate_settings(bad_interval) is not None
