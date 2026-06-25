# Tally Integration Guide

## Tally Settings

In Tally Prime:

1. Open the target company.
2. Enable Tally as a server on port `9000`.
3. Confirm inventory is maintained.
4. Confirm accounts and inventory are integrated.

In Setu:

1. Open `Settings`.
2. Add or activate the correct company profile.
3. Enter exact company, voucher type, ledger, GST ledger, round-off ledger, stock item, unit, and party names.
4. Leave `Enable Tally sync` off during setup.
5. Open `Tally Check`.
6. Confirm each required master only after comparing exact spelling in Tally.
7. Use a purchase/sale batch page to download the generated Tally XML.
8. Validate that XML against the real Tally company.
9. Enable sync only after validation.

Changing the active company disables sync again. Recheck that company's masters before posting live vouchers.

## Current Posting Support

Live XML posting is supported for:

- Purchase/receive
- Sale

These are queued until Tally sync is enabled.

The following local workflows are implemented but their Tally XML is intentionally not posted yet:

- Sales return
- Purchase return
- Issue

They remain `PENDING_SYNC` with a clear message until the exact voucher XML is configured.

## Required Setu Fields

Setu requires these fields before it can generate supported Tally XML:

- company name
- sales voucher type
- purchase voucher type
- sales ledger
- purchase ledger
- CGST ledger
- SGST ledger
- round-off ledger
- default party

Product masters must also have exact Tally stock item names and units.

## Sync Statuses

- `PENDING_SYNC`: sync is disabled, settings are incomplete, Tally is unreachable, or the voucher type is not configured for live posting.
- `FAILED`: Tally responded with a non-retryable error.
- `SYNCED`: Tally accepted the voucher.
- `CLOSED`: local-only workflows such as audit or barcode assignment completed without Tally posting.

Admins can open a batch to download XML, review sync attempts, and retry pending or failed supported batches.
