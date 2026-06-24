# User Manual

## Admin

- Create products.
- Generate barcode labels.
- Assign barcodes to existing Tally stock.
- Create users.
- Configure Tally settings.
- Run Tally Check.
- Monitor reports and pending sync.
- Download backups from Maintenance.

## Purchase User

1. Open `Purchase`.
2. Enter supplier/reference.
3. Scan all received serials.
4. Check the voucher preview.
5. Submit the batch.

## Sales User

1. Open `Sale`.
2. Enter customer/reference.
3. Scan all serials being sold.
4. Check the voucher preview.
5. Submit the batch.

## Auditor

1. Open `Audit`.
2. Enter location/reference.
3. Scan physical stock.
4. Submit the batch.
5. Review verified, missing, and extra serials.

## Returns and Issue

- `Sales return`: scan sold serials coming back from customer.
- `Purchase return`: scan in-stock serials being sent back to supplier.
- `Issue`: scan in-stock serials issued for samples, office use, damage, marketing, production, or other reasons.

Return and issue batches update local serial status. Tally XML for these voucher types is queued until the exact Tally format is configured and validated.

## Barcode Assignment

1. Open `Barcode Assignment`.
2. Select an existing product and quantity, or upload an Excel file with `Product Code` and `Quantity`.
3. Download the generated Excel file and labels PDF.

## Barcode Replacement

1. Open `Barcode Replace`.
2. Enter the old damaged serial.
3. Leave new serial blank to auto-generate, or enter a specific replacement serial.
4. Print the new label.
