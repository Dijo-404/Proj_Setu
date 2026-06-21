# Tally Integration Guide

## Tally Settings

In Tally Prime:

1. Open the target company.
2. Enable Tally as a server on port `9000`.
3. Confirm inventory is maintained.
4. Confirm accounts and inventory are integrated.

In Setu:

1. Open `Settings`.
2. Enter exact company, voucher type, ledger, stock item, unit, and party names.
3. Open `Tally Check`.
4. Confirm each required master.
5. Use a batch page to download the generated Tally XML.
6. Validate against the real Tally company.
7. Enable sync only after validation.

## Current Posting Support

Live XML posting is supported for:

- Receive
- Sale

These are queued until Tally sync is enabled.

The following local workflows are implemented but their Tally XML is intentionally not posted yet:

- Sales return
- Purchase return
- Issue

They remain `PENDING_SYNC` with a clear message until the exact voucher XML is configured.

