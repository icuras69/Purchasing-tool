# OP-44 Purchase Order Issue/Send Boundary

## Current issue behavior found

The current purchase-order workflow is local-only:

`draft -> pending_approval -> approved -> issued -> received/cancelled`

The `POST /purchase-orders/{po_id}/issue` endpoint:

- requires the PO to be in `approved` status
- runs OP-43 PO preflight
- sets `purchase_orders.status = "issued"`
- sets `purchase_orders.issued_at`
- commits the local database transaction

It does not:

- call OrderPro
- create an OrderPro purchase order
- email a supplier
- transmit a PO to any external system
- change inventory quantities
- receive stock

The previous frontend already warned that issue did not send externally, but the button label `Issue` could still sound like an outbound supplier action in a manager demo.

## Existing export support

PO CSV export exists at:

`GET /purchase-orders/{po_id}/export.csv`

The export is read-only and provides a manager/vendor-facing file, but exporting does not submit, approve, issue, send, or otherwise change the PO.

## Editing and cancellation behavior

Line editing is limited to `draft` purchase orders.

Cancellation is allowed for:

- `draft`
- `pending_approval`
- `approved`

Cancellation is not allowed after local `issued` or `received`.

## Safety risks before future external sending

Before adding any real OrderPro or supplier sending integration, the system still needs:

- a distinct external send action separate from local issue
- explicit external send audit records
- idempotency protection for outbound sends
- exact OrderPro payload validation
- supplier delivery/contact validation
- retry/failure handling
- permission checks around who may send externally
- a clear sent/failed/not-sent external state

## Endpoint added

`GET /purchase-orders/{purchase_order_id}/external-send-readiness`

This endpoint is read-only.

Current behavior:

- `external_send_supported=false`
- `external_send_system="OrderPro"`
- `can_send_externally=false`
- `required_local_status="issued"`
- message: `This purchase order is local-only. External OrderPro sending is not implemented yet.`

The endpoint also embeds a local preflight summary so the user can see whether the PO is locally clean, even though external sending is unavailable.

## Frontend changes

The approved-PO action now says:

`Mark as locally issued`

The helper text now states:

`Marking this PO as locally issued only changes the local status. It does not send to OrderPro, email suppliers, or create an external PO.`

A new PO detail panel appears:

`External Send Readiness`

It displays:

- external send supported
- can send externally
- target system
- required local status
- blockers
- warnings
- the explicit not-implemented message

No `Send to OrderPro` button was added.

## What still does not happen automatically

- No PO is sent externally.
- No OrderPro purchase order is created.
- No email is sent.
- No PO is automatically submitted, approved, or issued.
- No Render configuration changed.

## Recommended OP-45

Add an explicit external-send design document and backend-only dry-run payload preview for future OrderPro PO creation. The preview should produce the exact intended outbound payload without sending it and should require local `issued` status plus a passing external-send readiness check.
