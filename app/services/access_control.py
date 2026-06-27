from __future__ import annotations

from dataclasses import dataclass
import json

from sqlalchemy.orm import Session

from app.models import Role
from app.services.settings import get_setting, update_settings


SETTING_KEY = "role_access_config"
DENY_VALUES = {"hidden", "no"}
SUPER_ADMIN_ONLY_KEYS = {"page_role_access", "role_access_edit"}


@dataclass(frozen=True)
class RoleColumn:
    key: str
    label: str


@dataclass(frozen=True)
class AccessOption:
    value: str
    label: str


@dataclass(frozen=True)
class AccessCell:
    value: str
    label: str
    tone: str
    options: list[AccessOption]


@dataclass(frozen=True)
class AccessRowDefinition:
    key: str
    item: str
    context: str
    defaults: dict[str, str]
    options: list[AccessOption]
    note: str = ""


@dataclass(frozen=True)
class AccessRow:
    key: str
    item: str
    context: str
    cells: list[AccessCell]
    note: str = ""


@dataclass(frozen=True)
class AccessSectionDefinition:
    title: str
    context_heading: str
    rows: list[AccessRowDefinition]


@dataclass(frozen=True)
class AccessSection:
    title: str
    context_heading: str
    rows: list[AccessRow]


ROLE_COLUMNS = [
    RoleColumn(Role.SUPER_ADMIN.value, "Super admin"),
    RoleColumn(Role.ADMIN.value, "Admin"),
    RoleColumn(Role.PURCHASE.value, "Purchase"),
    RoleColumn(Role.SALES.value, "Sales"),
    RoleColumn(Role.AUDITOR.value, "Auditor"),
]

PAGE_OPTIONS = [AccessOption("shown", "Shown"), AccessOption("hidden", "Hidden")]
ACTION_OPTIONS = [AccessOption("edit", "Edit"), AccessOption("yes", "Yes"), AccessOption("no", "No")]
DATA_OPTIONS = [AccessOption("edit", "Edit"), AccessOption("view", "View"), AccessOption("workflow", "Workflow"), AccessOption("no", "No")]

CELL_META = {
    "shown": ("Shown", "synced"),
    "hidden": ("Hidden", "failed"),
    "edit": ("Edit", "synced"),
    "yes": ("Yes", "synced"),
    "view": ("View", "generated"),
    "workflow": ("Workflow", "pending_sync"),
    "no": ("No", "failed"),
}


def _roles(*roles: Role) -> list[str]:
    return [role.value for role in roles]


def _defaults(options: list[AccessOption], allowed_value: str, allowed_roles: list[str]) -> dict[str, str]:
    denied = "hidden" if options == PAGE_OPTIONS else "no"
    values = {role.key: denied for role in ROLE_COLUMNS}
    values[Role.SUPER_ADMIN.value] = allowed_value
    for role in allowed_roles:
        values[role] = allowed_value
    return values


def _all(options: list[AccessOption], value: str) -> dict[str, str]:
    return {role.key: value for role in ROLE_COLUMNS}


def _admin(options: list[AccessOption], value: str) -> dict[str, str]:
    return _defaults(options, value, _roles(Role.ADMIN))


def access_section_definitions() -> list[AccessSectionDefinition]:
    return [
        AccessSectionDefinition(
            title="Pages shown in navigation",
            context_heading="Where",
            rows=[
                AccessRowDefinition("page_dashboard", "Dashboard", "Top navigation", _all(PAGE_OPTIONS, "shown"), PAGE_OPTIONS),
                AccessRowDefinition("page_batches", "Batches", "Top navigation menu", _all(PAGE_OPTIONS, "shown"), PAGE_OPTIONS),
                AccessRowDefinition("page_serials", "Serials", "Top navigation", _all(PAGE_OPTIONS, "shown"), PAGE_OPTIONS),
                AccessRowDefinition("page_reports", "Reports", "Top navigation", _admin(PAGE_OPTIONS, "shown"), PAGE_OPTIONS),
                AccessRowDefinition("page_tally_check", "Tally Check", "Top navigation", _admin(PAGE_OPTIONS, "shown"), PAGE_OPTIONS),
                AccessRowDefinition("page_barcodes", "Barcodes", "Top navigation menu", _admin(PAGE_OPTIONS, "shown"), PAGE_OPTIONS),
                AccessRowDefinition("page_admin_menu", "Admin menu", "Top navigation menu", _admin(PAGE_OPTIONS, "shown"), PAGE_OPTIONS),
                AccessRowDefinition(
                    "page_products",
                    "Products",
                    "Admin menu",
                    _admin(PAGE_OPTIONS, "shown"),
                    PAGE_OPTIONS,
                    "Product search can still be opened directly by signed-in users when Product master data is allowed.",
                ),
                AccessRowDefinition("page_expiry", "Expiry", "Admin menu", _admin(PAGE_OPTIONS, "shown"), PAGE_OPTIONS),
                AccessRowDefinition("page_settings", "Settings", "Admin menu", _admin(PAGE_OPTIONS, "shown"), PAGE_OPTIONS),
                AccessRowDefinition(
                    "page_role_access",
                    "Role access",
                    "Admin menu",
                    _defaults(PAGE_OPTIONS, "shown", []),
                    PAGE_OPTIONS,
                    "Locked to super admin so other roles cannot change their own access.",
                ),
                AccessRowDefinition("page_maintenance", "Maintenance", "Admin menu", _admin(PAGE_OPTIONS, "shown"), PAGE_OPTIONS),
                AccessRowDefinition("page_users", "Users", "Admin menu", _admin(PAGE_OPTIONS, "shown"), PAGE_OPTIONS),
            ],
        ),
        AccessSectionDefinition(
            title="Actions allowed by role",
            context_heading="Action",
            rows=[
                AccessRowDefinition("batch_purchase", "Purchase batch", "Create, scan, edit draft, submit", _defaults(ACTION_OPTIONS, "edit", _roles(Role.ADMIN, Role.PURCHASE)), ACTION_OPTIONS),
                AccessRowDefinition("batch_sale", "Sale batch", "Create, scan, edit draft, submit", _defaults(ACTION_OPTIONS, "edit", _roles(Role.ADMIN, Role.SALES)), ACTION_OPTIONS),
                AccessRowDefinition("batch_audit", "Audit batch", "Create, scan, submit, download audit PDF", _defaults(ACTION_OPTIONS, "edit", _roles(Role.ADMIN, Role.AUDITOR)), ACTION_OPTIONS),
                AccessRowDefinition("batch_sales_return", "Sales return", "Create, scan, edit draft, submit", _defaults(ACTION_OPTIONS, "edit", _roles(Role.ADMIN, Role.SALES)), ACTION_OPTIONS),
                AccessRowDefinition("batch_purchase_return", "Purchase return", "Create, scan, edit draft, submit", _defaults(ACTION_OPTIONS, "edit", _roles(Role.ADMIN, Role.PURCHASE)), ACTION_OPTIONS),
                AccessRowDefinition("batch_issue", "Stock issue", "Create, scan, edit draft, submit", _admin(ACTION_OPTIONS, "edit"), ACTION_OPTIONS),
                AccessRowDefinition("manual_serial_entry", "Manual serial entry", "Type serial numbers into batches", _admin(ACTION_OPTIONS, "edit"), ACTION_OPTIONS, "Non-admin users can scan by camera/photo only."),
                AccessRowDefinition("fefo_pick", "FEFO pick", "Auto-pick sale, issue, purchase return", _defaults(ACTION_OPTIONS, "edit", _roles(Role.ADMIN, Role.PURCHASE, Role.SALES)), ACTION_OPTIONS),
                AccessRowDefinition("tally_xml", "Tally XML", "Download purchase/sale XML", _admin(ACTION_OPTIONS, "yes"), ACTION_OPTIONS),
                AccessRowDefinition("tally_sync_retry", "Tally sync retry", "Retry pending or failed sync", _admin(ACTION_OPTIONS, "yes"), ACTION_OPTIONS),
                AccessRowDefinition("product_create", "Products", "Create products and generate serials", _admin(ACTION_OPTIONS, "edit"), ACTION_OPTIONS),
                AccessRowDefinition("barcode_assignment", "Barcode assignment", "Assign labels to existing stock", _admin(ACTION_OPTIONS, "edit"), ACTION_OPTIONS),
                AccessRowDefinition("barcode_replacement", "Barcode replacement", "Replace damaged serial labels", _admin(ACTION_OPTIONS, "edit"), ACTION_OPTIONS),
                AccessRowDefinition("reports_export", "Reports", "Filter and export scan/transaction reports", _admin(ACTION_OPTIONS, "yes"), ACTION_OPTIONS),
                AccessRowDefinition("tally_check_edit", "Tally Check", "Confirm, refresh, and remove master checks", _admin(ACTION_OPTIONS, "edit"), ACTION_OPTIONS),
                AccessRowDefinition("settings_edit", "Settings", "Edit company settings and enable sync", _admin(ACTION_OPTIONS, "edit"), ACTION_OPTIONS),
                AccessRowDefinition(
                    "role_access_edit",
                    "Role access",
                    "Edit role permission matrix",
                    _defaults(ACTION_OPTIONS, "edit", []),
                    ACTION_OPTIONS,
                    "Locked to super admin.",
                ),
                AccessRowDefinition(
                    "users_manage",
                    "Users",
                    "Create users and enable/disable accounts",
                    _admin(ACTION_OPTIONS, "edit"),
                    ACTION_OPTIONS,
                    "Only super admins can delete user accounts. Accounts with history are hidden and kept for old records.",
                ),
                AccessRowDefinition("backup_download", "Backup", "Download SQLite backup", _admin(ACTION_OPTIONS, "yes"), ACTION_OPTIONS),
            ],
        ),
        AccessSectionDefinition(
            title="Data access and modification",
            context_heading="Data area",
            rows=[
                AccessRowDefinition("dashboard_data", "Dashboard data", "Counts, charts, recent scans and batches", _all(DATA_OPTIONS, "view"), DATA_OPTIONS),
                AccessRowDefinition("product_master", "Product master", "View product list/search", _all(DATA_OPTIONS, "view"), DATA_OPTIONS, "Only users with Product action access can create products or generate serials."),
                AccessRowDefinition("serial_data", "Serial data", "View serial list, details, scan history", _all(DATA_OPTIONS, "view"), DATA_OPTIONS),
                AccessRowDefinition("label_files", "Label files", "Download serial XLSX or admin label PDF", _defaults(DATA_OPTIONS, "view", _roles(Role.ADMIN, Role.PURCHASE, Role.SALES, Role.AUDITOR)), DATA_OPTIONS),
                AccessRowDefinition("batch_list", "Batch list", "View all recent batches", _all(DATA_OPTIONS, "view"), DATA_OPTIONS, "Batch detail pages still follow batch-type permissions."),
                AccessRowDefinition("purchase_data", "Purchase data", "Purchase and purchase-return batches", _defaults(DATA_OPTIONS, "workflow", _roles(Role.ADMIN, Role.PURCHASE)), DATA_OPTIONS),
                AccessRowDefinition("sales_data", "Sales data", "Sale and sales-return batches", _defaults(DATA_OPTIONS, "workflow", _roles(Role.ADMIN, Role.SALES)), DATA_OPTIONS),
                AccessRowDefinition("audit_data", "Audit data", "Audit batches and findings", _defaults(DATA_OPTIONS, "workflow", _roles(Role.ADMIN, Role.AUDITOR)), DATA_OPTIONS),
                AccessRowDefinition("issue_data", "Issue data", "Stock issue batches", _admin(DATA_OPTIONS, "edit"), DATA_OPTIONS),
                AccessRowDefinition("reports_data", "Reports data", "Scan logs and inventory transactions", _admin(DATA_OPTIONS, "view"), DATA_OPTIONS),
                AccessRowDefinition("expiry_analytics", "Expiry analytics", "Expiry risk and sleeping stock", _admin(DATA_OPTIONS, "view"), DATA_OPTIONS),
                AccessRowDefinition("tally_settings", "Tally settings", "Company profiles, ledgers, sync flag", _admin(DATA_OPTIONS, "edit"), DATA_OPTIONS),
                AccessRowDefinition("tally_attempts", "Tally sync attempts", "Request/response details", _admin(DATA_OPTIONS, "view"), DATA_OPTIONS),
                AccessRowDefinition("user_accounts", "User accounts", "User list, roles, active status", _admin(DATA_OPTIONS, "edit"), DATA_OPTIONS),
                AccessRowDefinition("backup_data", "Backup data", "SQLite database download", _admin(DATA_OPTIONS, "view"), DATA_OPTIONS),
            ],
        ),
    ]


def _definitions_by_key() -> dict[str, AccessRowDefinition]:
    return {row.key: row for section in access_section_definitions() for row in section.rows}


def default_role_access_config() -> dict[str, dict[str, str]]:
    return {key: row.defaults.copy() for key, row in _definitions_by_key().items()}


def _valid_option(row: AccessRowDefinition, value: str) -> bool:
    return value in {option.value for option in row.options}


def normalize_role_access_config(raw_config: dict | None) -> dict[str, dict[str, str]]:
    definitions = _definitions_by_key()
    config = default_role_access_config()
    raw_config = raw_config if isinstance(raw_config, dict) else {}
    for row_key, row_values in raw_config.items():
        row = definitions.get(row_key)
        if not row or not isinstance(row_values, dict):
            continue
        for role in ROLE_COLUMNS:
            if role.key == Role.SUPER_ADMIN.value:
                continue
            value = str(row_values.get(role.key, "")).strip()
            if _valid_option(row, value):
                config[row_key][role.key] = value
    for row_key, row in definitions.items():
        config[row_key][Role.SUPER_ADMIN.value] = row.defaults[Role.SUPER_ADMIN.value]
        if row_key in SUPER_ADMIN_ONLY_KEYS:
            denied = "hidden" if row.options == PAGE_OPTIONS else "no"
            for role in ROLE_COLUMNS:
                if role.key != Role.SUPER_ADMIN.value:
                    config[row_key][role.key] = denied
    return config


def get_role_access_config(db: Session) -> dict[str, dict[str, str]]:
    raw = get_setting(db, SETTING_KEY, "")
    if not raw:
        return default_role_access_config()
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return default_role_access_config()
    return normalize_role_access_config(parsed)


def save_role_access_config(db: Session, submitted: dict[str, dict[str, str]]) -> None:
    config = get_role_access_config(db)
    for row_key, row_values in submitted.items():
        config.setdefault(row_key, {}).update(row_values)
    config = normalize_role_access_config(config)
    update_settings(db, {SETTING_KEY: json.dumps(config, sort_keys=True)})


def config_from_form(form_items) -> dict[str, dict[str, str]]:
    definitions = _definitions_by_key()
    config: dict[str, dict[str, str]] = {}
    for key, value in form_items:
        if not key.startswith("access__"):
            continue
        parts = key.split("__", 2)
        if len(parts) != 3:
            continue
        _, row_key, role_key = parts
        row = definitions.get(row_key)
        if not row or role_key == Role.SUPER_ADMIN.value:
            continue
        value = str(value).strip()
        if _valid_option(row, value):
            config.setdefault(row_key, {})[role_key] = value
    return config


def _cell(value: str, options: list[AccessOption]) -> AccessCell:
    label, tone = CELL_META.get(value, (value.title(), "generated"))
    return AccessCell(value=value, label=label, tone=tone, options=options)


def role_access_sections(db: Session | None = None) -> list[AccessSection]:
    config = get_role_access_config(db) if db is not None else default_role_access_config()
    sections: list[AccessSection] = []
    for section in access_section_definitions():
        rows = []
        for row in section.rows:
            row_config = config.get(row.key, row.defaults)
            rows.append(
                AccessRow(
                    key=row.key,
                    item=row.item,
                    context=row.context,
                    note=row.note,
                    cells=[_cell(row_config.get(role.key, row.defaults[role.key]), row.options) for role in ROLE_COLUMNS],
                )
            )
        sections.append(AccessSection(section.title, section.context_heading, rows))
    return sections


def role_access_value(db: Session, role: Role | str, access_key: str) -> str:
    role_value = role.value if isinstance(role, Role) else str(role)
    if role_value == Role.SUPER_ADMIN.value:
        return "edit"
    config = get_role_access_config(db)
    row = config.get(access_key)
    if not row:
        return "no"
    return row.get(role_value, "no")


def configured_role_has_access(
    config: dict[str, dict[str, str]],
    role: Role | str,
    access_key: str,
    allowed_values: set[str] | None = None,
) -> bool:
    role_value = role.value if isinstance(role, Role) else str(role)
    if role_value == Role.SUPER_ADMIN.value:
        value = "edit"
    else:
        value = config.get(access_key, {}).get(role_value, "no")
    if value in DENY_VALUES:
        return False
    if allowed_values is not None:
        return value in allowed_values
    return True


def landing_path_for(config: dict[str, dict[str, str]], role: Role | str) -> str:
    can = lambda key: configured_role_has_access(config, role, key)
    destinations = [
        ("page_dashboard", "dashboard_data", "/"),
        ("page_batches", "batch_list", "/batches"),
        ("page_batches", "batch_purchase", "/batches/new?batch_type=PURCHASE"),
        ("page_batches", "batch_sale", "/batches/new?batch_type=SALE"),
        ("page_batches", "batch_audit", "/batches/new?batch_type=AUDIT"),
        ("page_serials", "serial_data", "/serials"),
        ("page_reports", "reports_data", "/reports"),
        ("page_tally_check", "tally_check_edit", "/tally-check"),
        ("page_barcodes", "barcode_assignment", "/barcode-assignment"),
        ("page_barcodes", "barcode_replacement", "/barcode-replacement"),
        ("page_products", "product_master", "/products"),
        ("page_expiry", "expiry_analytics", "/expiry"),
        ("page_settings", "settings_edit", "/settings"),
        ("page_maintenance", "backup_data", "/maintenance"),
        ("page_users", "users_manage", "/users"),
    ]
    for page_key, permission_key, path in destinations:
        if can(page_key) and can(permission_key):
            return path
    if str(role) in {Role.SUPER_ADMIN.value, str(Role.SUPER_ADMIN)}:
        return "/settings/access"
    return "/account/password"


def role_has_access(db: Session, role: Role | str, access_key: str, allowed_values: set[str] | None = None) -> bool:
    return configured_role_has_access(get_role_access_config(db), role, access_key, allowed_values)
