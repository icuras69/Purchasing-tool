# OP-45 Local Purchase Workflow Smoke Test

## Scope

OP-45 adds backend smoke coverage for the hardened local purchasing workflow from recommendation review through local PO issue. The tests use isolated pytest database fixtures and synthetic products, suppliers, demand rows, recommendations, and purchase orders.

No script was added. A standalone smoke script would be easy to run against the wrong database, so pytest fixtures are the safer test boundary for now.

## Current workflow audited

The local workflow is:

1. Forecast and recommendation audit decides whether a product can be reordered.
2. Stale-only demand remains blocked unless a manager records `manager_approved_one_time`.
3. A manager-approved stale product can enter the manager-approved stale queue and create a pending-review recommendation.
4. A recommendation must be explicitly accepted before conversion.
5. `GET /recommendations/{recommendation_id}/po-readiness` confirms draft PO eligibility.
6. `POST /recommendations/{recommendation_id}/convert-to-draft-po` creates a local draft PO only.
7. `GET /purchase-orders/{purchase_order_id}/preflight` validates the draft PO before transitions.
8. Submit, approve, and issue all run preflight before status changes.
9. `issued` is a local status only. It does not call OrderPro, email suppliers, or send any external purchase order.
10. `GET /purchase-orders/{purchase_order_id}/external-send-readiness` always reports `external_send_supported=false` and `can_send_externally=false` for now.

## Happy path verified

`test_smoke_recent_demand_recommendation_to_local_issued_po` verifies the normal recent-demand path:

- Synthetic OrderPro product with canonical `products.supplier_id`.
- Recent shipped OrderPro demand.
- Backend creates a pending review recommendation.
- Manager accepts the recommendation.
- PO readiness passes using canonical supplier source `products.supplier_id`.
- Conversion creates a local draft PO with `product_id` populated and no legacy `product_supplier_id`.
- PO preflight passes.
- PO transitions through `draft -> pending_approval -> approved -> issued`.
- External send readiness remains disabled before and after issue.

## Stale manager-approved path verified

`test_smoke_manager_approved_stale_demand_to_local_issued_po` verifies the stale-demand path:

- Synthetic product has only stale legacy demand.
- Conversion is blocked before a manager decision.
- Manager records `manager_approved_one_time`.
- Product appears in the manager-approved stale queue as ready for manual recommendation review.
- Queue creates a pending review recommendation.
- Manager accepts the recommendation.
- PO readiness passes while preserving stale-demand warnings.
- Conversion creates a local draft PO.
- PO preflight retains the stale-demand warning.
- PO transitions through local submit, approve, and issue.
- No external send becomes available.

## Blocked cases verified

`test_smoke_recommendation_to_po_hard_blockers` verifies recommendation-to-PO blockers:

- Missing canonical direct supplier blocks conversion even when a legacy `ProductSupplier` mapping exists.
- Missing lead time blocks conversion.
- Non-positive recommended quantity blocks conversion.
- Monitor/no-reorder forecast action blocks conversion.
- Stale-only demand without `manager_approved_one_time` blocks conversion.

`test_smoke_po_preflight_blocks_bad_purchase_orders` verifies PO-level blockers:

- Draft PO with no lines cannot submit.
- Mixed-supplier PO cannot submit.
- Line with non-positive quantity cannot submit.
- Approved flow cannot continue when a line becomes invalid before approval.

`test_smoke_local_issue_never_enables_external_send` verifies the external boundary:

- A valid PO can be locally submitted, approved, and issued.
- External send readiness remains unsupported and false.
- The local issue response is marked local-only.

## PO statuses verified

The smoke tests verify:

- `draft`
- `pending_approval`
- `approved`
- `issued`

They do not verify receive or cancel behavior because OP-45 focuses on the local recommendation-to-issue flow and external-send safety.

## External-send boundary verified

The tests monkeypatch the OrderPro client read method to raise if called. The smoke paths run without triggering OrderPro. External send readiness continues to report:

- `external_send_supported=false`
- `external_send_system=OrderPro`
- `can_send_externally=false`
- Message: `This purchase order is local-only. External OrderPro sending is not implemented yet.`

## Remaining risks

- Smoke tests validate the backend behavior, not the visual browser flow.
- External sending is not implemented; future OrderPro push work needs a separate explicit design, credentials policy, dry-run mode, and approval flow.
- Cost and pack-size warnings remain advisory by default. If the business later requires either one, configuration and tests should be rerun with those requirements enabled.
- The tests use synthetic data and do not mutate the user's local business database.

## Recommended OP-46

Add an operator-facing "PO handoff packet" for locally issued purchase orders: CSV/PDF export, supplier contact details, local-only warning, and an audit trail showing recommendation, readiness, preflight, manager stale decision if applicable, and issue timestamp. Keep it export-only until a controlled external send integration is designed.
