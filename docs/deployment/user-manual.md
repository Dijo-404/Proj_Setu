# User Manual

Setu is used from a browser on the factory LAN. Staff sign in, scan barcode serials, and submit stock movements. Tally remains the accounting and inventory master; Setu keeps serial-level traceability and posts only the supported voucher types after admin validation.

## Common Navigation

- `Dashboard`: stock counts, pending sync, recent scans, recent batches, charts, and expiry summary.
- `Batches`: purchase, sale, audit, sales return, purchase return, issue, and all batches.
- `Serials`: search serials, view serial history, and open label pages.
- `Reports`: admin-only scan and transaction reports with CSV/XLSX exports.
- `Barcodes`: admin-only assignment and replacement tools.
- `Admin`: products, expiry, settings, maintenance, and users.

## Roles

- `admin` and `super_admin`: full setup, products, labels, assignment, replacement, reports, Tally settings, sync retry, maintenance, and users.
- `purchase`: purchase and purchase-return batches.
- `sales`: sale and sales-return batches.
- `auditor`: audit batches.

Manual serial entry is admin-only. Non-admin users should use the camera or photo scan controls.

Admins can open `Settings` -> `Role access` to review and change which pages are shown, which actions each role can perform, and what data each role can view or modify.

## Admin Setup

1. Open `Settings`.
2. Add or activate a company profile.
3. Enter exact Tally names for company, voucher types, ledgers, GST ledgers, round-off ledger, and default party.
4. Keep `Enable Tally sync` off until setup is validated.
5. Open `Products` and create product masters with exact Tally stock item names.
6. Open `Tally Check` and confirm each required master only after comparing with Tally.
7. Create named users from `Users`.

Settings fields auto-save while editing. The sync checkbox is saved only by the `Save settings` button and is blocked until Tally Check is complete.

## Products and Labels

1. Open `Products`.
2. Create or search product masters.
3. Use `Generate Barcode` to create serials.
4. Choose `Generated` for labels that are not yet in stock.
5. Choose `Existing stock` for physical stock already present in the factory.
6. Add product batch and expiry details when they are known.
7. Open the generated assignment batch to download labels PDF or serial XLSX.

Labels contain only the barcode and serial text. They do not include price, GST, customer, or product data.

## Barcode Assignment

Use `Barcodes` -> `Assignment` to inward existing stock into Setu without a purchase scan.

Single-product assignment:

1. Select the product.
2. Enter quantity.
3. Optional: prefix, product batch, warehouse, manufacturing date, expiry date, and notes.
4. Generate barcodes.

Bulk assignment accepts `.xlsx` files up to 5 MB with these columns:

```text
Product Code, Quantity, Batch, Mfg Date, Expiry Date, Warehouse
```

Download the assignment's label PDF and serial XLSX after generation.

## Barcode Replacement

1. Open `Barcodes` -> `Replacement`.
2. Enter the old damaged serial.
3. Leave new serial blank to auto-generate, or enter a specific replacement serial.
4. Add a reason.
5. Print the new label from the result.

The old serial is marked inactive/replaced and the new serial is linked to it.

## Purchase

1. Open `Batches` -> `Purchase`.
2. Enter supplier/reference details.
3. Scan generated or purchase-return serials.
4. Confirm rates in the voucher preview.
5. Submit the batch.

Submitted purchase serials become `IN_STOCK`.

## Sale

1. Open `Batches` -> `Sale`.
2. Enter customer/reference details.
3. Scan in-stock serials, or use `Pick FEFO` for product and quantity.
4. Confirm rates, GST split, round off, and final invoice value.
5. Submit the batch.

Submitted sale serials become `SOLD`.

## Audit

1. Open `Batches` -> `Audit`.
2. Enter location/reference details.
3. Scan physical stock.
4. Submit the batch.
5. Review verified, missing, and extra findings.
6. Download the audit PDF when needed.

## Returns and Issue

- `Sales return`: scan sold serials coming back from a customer. Damaged or expired returns can be marked with an appropriate reason.
- `Purchase return`: scan or FEFO-pick in-stock serials being sent back to a supplier.
- `Issue`: scan or FEFO-pick in-stock serials issued for samples, office use, damage, marketing, production, or other reasons.

Return and issue batches update local serial status. Their Tally XML is intentionally not posted until the client's exact voucher format is validated.

## Expiry Control

Open `Admin` -> `Expiry` to review:

- stock expiring within the configured horizon
- slow-moving expiry risk
- sleeping stock
- warehouse expiry exposure
- FEFO sale shortcut
- product batch entry shortcut

For sale, issue, and purchase-return batches, Setu enforces FEFO when expiry dates are available.

## Reports

Admins can open `Reports` to review:

- scan history
- transaction history
- pending and failed sync batches
- expiry summary context
- CSV/XLSX exports

Open a serial detail page to see the full scan and transaction history for one serial.

## Backup

1. Log in as admin.
2. Open `Admin` -> `Maintenance`.
3. Click `Download backup`.
4. Store the downloaded `.db` file safely.

Scheduled server backups should include the whole `data/` folder and a separate copy of `.env`.
