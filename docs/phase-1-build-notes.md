# Phase 1 Build Notes

## Implemented scope

- FastAPI application shell
- SQLite schema
- Session-cookie authentication
- User management
- Product management
- QR serial generation
- Printable labels
- Receive batches
- Sale batches
- Audit batches
- Scan history
- Reports and CSV export
- Tally settings
- Tally master readiness checklist
- Tally gateway test
- Tally XML sync attempts with queue status
- Automatic pending-sync retry worker
- Retry count and last retry tracking
- Persisted audit reconciliation findings
- XLSX scan report export
- PDF QR labels and audit reports
- SQLite-safe backup download and restore procedure
- Live-sync gate tied to Tally Check readiness
- Tally XML preview and sync-attempt request/response viewer
- Sales return, purchase return, and stock issue workflows
- QR replacement with inactive old serial and linked replacement serial
- Deployment guides and Windows service helper

## Deliberate boundaries

- Returns, issue, and replacement are modeled in the schema but not enabled as active workflows yet.
- Tally sync defaults to disabled to avoid posting against unknown ledger names.
- Serial-level detail stays local. Tally receives aggregate voucher quantities by product.

## Next build slice

- Real Tally validation on the client's machine.
