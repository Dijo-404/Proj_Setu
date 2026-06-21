# Setu QR Tally Bridge

Setu is a LAN-first QR transaction bridge for Tally Prime. It captures product-level QR scans from phones, keeps serial history locally, and syncs purchase/sales stock movements to Tally through its XML gateway.

## What is built

- Role-based login for super admin, admin, purchase, sales, and auditor users.
- Product master with HSN, GST, unit, default rate, and exact Tally stock item name.
- Bulk QR serial generation with printable labels.
- Batch-based receive, sale, and audit workflows.
- Phone camera scanning through the browser `BarcodeDetector` API, with manual entry fallback.
- Serial state validation to prevent duplicate receiving and double selling.
- Local scan logs and transaction history.
- Tally XML request generation, response capture, retry tracking, and pending sync queue.
- Admin reports with CSV export.
- Tally settings screen for company, host, port, voucher types, and ledger names.
- Tally Check screen for master readiness, exact-name confirmation, and gateway testing.
- Automatic retry worker for `PENDING_SYNC` batches, with retry count and last retry time.
- Audit reconciliation for verified, missing, and extra serials.
- XLSX scan report export plus PDF QR labels and audit reports.
- Admin maintenance page with SQLite-safe backup download and restore procedure.
- Sales return, purchase return, and stock issue workflows with reason codes.
- QR replacement workflow with linked old/new serial history.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

Default bootstrap login:

```text
username: admin
password: admin123
```

Change `APP_SECRET_KEY` and the bootstrap password before deployment.

## Tally mode

Tally sync is disabled by default. Submitted receive and sale batches are stored as `PENDING_SYNC` until an admin enables Tally sync in Settings.

When Tally sync is enabled, a background worker retries pending batches at the interval configured in Settings. Manual retry remains available on each pending or failed batch.

Before enabling sync, confirm exact Tally master names:

- Company name
- Stock item names
- Unit names
- Sales and purchase voucher type names
- Sales and purchase ledger names
- GST ledger names
- Round off ledger name

Use `Tally Check` in the app to review these names, mark them confirmed, and test whether the Tally HTTP gateway responds.

Live sync cannot be enabled until Tally Check has no missing or unchecked masters. Batch pages also expose a Tally XML download for validating the generated voucher envelope against the real Tally company.

Tally Prime must be running as a server on port `9000`, with inventory and accounting integration enabled.

## Phase 1 workflow

1. Admin creates products.
2. Admin generates QR serials.
3. Purchase user starts a receive batch and scans serials.
4. Sales user starts a sale batch and scans in-stock serials.
5. Auditor starts an audit batch and scans physical stock.
6. Admin monitors reports and pending sync.

Sales and receive batches submit as one transaction per batch, not one voucher per scanned unit.

## Deployment notes

For phone camera access on a LAN hostname or IP, serve the app over HTTPS. For the factory deployment, use a local reverse proxy such as Caddy or nginx with a locally trusted certificate.

The SQLite database is stored at `data/setu.db` by default. Use Maintenance to download a safe backup, and keep `.env` backed up separately.

Deployment guides are in `docs/deployment/`.
