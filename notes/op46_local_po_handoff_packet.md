# OP-46 Local PO Handoff Packet

## Purpose

OP-46 adds a local-only handoff packet for purchase orders that have already been issued inside the Purchasing Tool. The packet is intended for manual review or external handling outside the application.

## Eligibility

Only purchase orders with local status `issued` can generate a handoff packet. Draft, pending approval, approved-but-not-issued, cancelled, and other non-issued states are rejected with a domain error.

The feature preserves the existing local issue boundary and does not alter purchase order workflow transitions.

## Packet Contents

The download is a deterministic ZIP archive containing:

- `purchase_order.json`: packet schema version, generated timestamp, local PO identity, local status, issue and approval dates when available, supplier details, totals, line count, false external-send flags, and any already-populated local OrderPro linkage fields.
- `purchase_order_lines.csv`: one row per PO line with local line and product IDs, stored OrderPro product identifiers, SKU, product name, ordered quantity, unit cost, line total, currency, pack quantity, number of packs, MOQ, order multiple, and pack-rule adjustment reason when available.
- `README.txt`: plain-language handling notes and file descriptions.

## API And UI Behavior

The backend exposes:

`GET /purchase-orders/{purchase_order_id}/handoff-packet`

The response is `application/zip` with a sanitized attachment filename such as `purchase-order-po-500-handoff.zip`.

The frontend shows `Download handoff packet` only for issued purchase orders. The UI note states that downloading the packet does not send the purchase order externally or create an OrderPro purchase order.

## Security Boundary

The handoff packet is GET-only and local-only. It does not call OrderPro, use OrderPro tokens, create or submit an external purchase order, update supplier data, update product data, or change local PO status.

The packet includes local OrderPro linkage fields only when those fields are already populated locally.

## Tests

Backend coverage verifies successful ZIP generation, filename and content type, required files, JSON flags, CSV values and totals, pack and MOQ fields, ineligible status rejection, unchanged PO status, and that no OrderPro client call is made.

Frontend coverage verifies issued-only button visibility, download behavior, user-facing copy, and API filename handling.

## Manual Verification

1. Create or locate a locally issued purchase order with line items.
2. Open the purchase order detail view.
3. Confirm `Download handoff packet` is visible only after the PO is issued.
4. Download the ZIP and confirm it contains `purchase_order.json`, `purchase_order_lines.csv`, and `README.txt`.
5. Confirm the README states no OrderPro PO was created and nothing was sent externally.
6. Confirm the local PO status and OrderPro linkage fields remain unchanged.

## Deferred

OrderPro write-back remains deliberately deferred. OP-46 does not send, submit, create, or update any OrderPro purchase order.

Persistent audit logging for handoff packet generation is also deferred because the current audit framework is focused on recommendation and forecast review records rather than non-state-changing PO exports. Adding durable PO export audit records would require a new persistence path and likely a migration, which is outside this task's narrow boundary.
