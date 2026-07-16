# OP-43 Purchase Order Detail Preflight

## Current workflow found

Purchase orders are local records in `purchase_orders` with line items in `purchase_order_lines`.

Current statuses:

- `draft`
- `pending_approval`
- `approved`
- `issued`
- `received`
- `cancelled`

Draft POs are created directly from a supplier, from selected products, from supplier forecasts, or from accepted recommendations. Existing line creation supports direct `products.supplier_id` product lines and legacy `product_suppliers` snapshots for compatibility.

Recommendation-created lines are represented as normal purchase-order lines. The recommendation may reference the converted PO through `Recommendation.converted_purchase_order_id`; preflight uses that link to identify manager-approved one-time stale-demand recommendation context where available.

Line `product_id` is required by the model. `product_supplier_id` can still appear on older or compatibility lines, but it is now treated as a warning source rather than the canonical supplier source. Canonical supplier validation uses `products.supplier_id`.

Unit cost is snapshotted on purchase-order lines when available. Cost is optional by default; if `RECOMMENDATION_REQUIRE_COST=true`, missing unit cost blocks transitions. Supplier identity is stored on the PO through `purchase_orders.supplier_id`; the frontend displays `supplier_name` from the backend serializer.

Before OP-43, submit/approve primarily validated status and, for approval, line presence. It did not run canonical supplier, product, quantity, cost, pack-size, or mixed-supplier checks immediately before status changes.

## Endpoint added

`GET /purchase-orders/{purchase_order_id}/preflight`

The endpoint is read-only and returns:

- purchase order id, status, supplier id/name
- `can_submit`
- `can_approve`
- `can_issue_if_applicable`
- `overall_status`: `ready`, `needs_review`, or `blocked`
- top-level blockers and warnings
- line-level checks
- summary counts

## Blocker rules

Preflight blocks when:

- the PO has no supplier
- the supplier is inactive, if the model exposes `is_active`
- the PO has no lines
- a line has no canonical product validation path
- a line product is missing
- a line product is non-inventory
- a line product has no canonical `products.supplier_id`
- a line canonical supplier conflicts with the PO supplier
- multiple canonical suppliers appear on one PO
- line quantity is missing, zero, or negative
- unit cost is missing while cost is configured as required
- pack size is missing while pack size is configured as required
- the PO status does not allow the requested transition

## Warning rules

Preflight warns when:

- unit cost is missing and cost is optional
- pack size is missing and pack size is optional
- MOQ is missing or non-positive, indicating a fallback may have been used
- supplier SKU is missing
- product name snapshot differs from the current product name
- a line uses legacy `product_supplier_id`
- a line originated from a manager-approved one-time stale-demand recommendation

## Submit, approval, and issue gating

Submit now runs preflight and requires `can_submit=true`.

Approve now runs preflight and requires `can_approve=true`.

Issue now also runs preflight and requires `can_issue_if_applicable=true`, because issuing may later become the boundary before external sending. This remains local-only and does not call OrderPro.

The frontend PO detail screen shows a compact "PO Preflight" panel and disables Submit/Approve only when the loaded preflight result says the action is blocked. If the preflight request fails, the panel shows a non-blocking warning and the backend remains the final authority.

## What still does not happen automatically

- No PO is submitted automatically.
- No PO is approved automatically.
- No PO is issued automatically.
- No PO is sent to OrderPro.
- No recommendation is automatically converted because of preflight.
- Stale-demand policy is not globally relaxed.

## Risks addressed

- Draft POs with no lines can no longer be submitted.
- Pending POs with incomplete lines can no longer be approved.
- Lines with legacy mapping data alone cannot bypass canonical supplier validation.
- Mixed supplier lines are blocked before submit/approval/issue.
- Missing optional commercial data is visible without blocking unless configured.

## Recommended OP-44

Add a final PO issue/send readiness audit that distinguishes local `issued` status from any future external OrderPro send workflow, including a clear "not sent externally" state and exportable manager approval evidence.
