# OP-41 Purchase Order Workflow Hardening

## Current workflow found

Purchase orders can be created directly as local drafts through `POST /purchase-orders`, from selected products through `POST /purchase-orders/draft-from-products`, and from accepted recommendations through `POST /recommendations/{recommendation_id}/convert-to-draft-po`.

The product-based draft flow already uses the direct OrderPro supplier assignment on `products.supplier_id` and creates PO lines with `product_id` populated and `product_supplier_id` left null. The manual PO line route still supports legacy `product_supplier_id` for backward compatibility, but it also supports the canonical `product_id` path and validates that the product supplier matches the PO supplier.

Before OP-41, recommendation-to-PO conversion still required a legacy `ProductSupplier` mapping. That meant modern OrderPro-sourced recommendations with `product_supplier_id = null` could not convert even when `products.supplier_id` was valid.

## Validation added

Recommendation-to-PO conversion now runs a canonical PO readiness check before creating a draft PO. A recommendation can create a draft PO only when:

- Recommendation status is `accepted`.
- Recommendation type is `reorder`.
- Product exists and is an inventory product.
- Product has canonical supplier assignment through `products.supplier_id`.
- The canonical supplier exists and is active.
- Stored recommendation supplier, when present, does not conflict with the product canonical supplier.
- Recommended quantity is positive.
- Forecast action is `reorder`.
- Missing supplier, missing lead time, and no demand/open demand are not present as hard blockers.
- Stale-only demand has an explicit latest decision of `manager_approved_one_time`.
- Missing cost blocks only when cost is configured as required.
- Missing pack size blocks only when pack size is configured as required.

Warnings remain visible but do not block when the current policy treats them as advisory:

- Missing pack size when optional.
- Missing cost when optional.
- Fallback MOQ.
- Quantity raised to MOQ.
- Quantity rounded to pack size.
- Returns or negative demand warnings.
- Manager-approved stale-only demand warning.

## Canonical supplier source

The canonical supplier source for recommendation-to-PO conversion is:

```text
products.supplier_id
```

Legacy `product_suppliers` rows no longer allow recommendation conversion by themselves. They remain available only in older/manual workflows where already supported.

## PO readiness endpoint

Added:

```text
GET /recommendations/{recommendation_id}/po-readiness
```

The endpoint is read-only and returns:

- Recommendation and product identity.
- Canonical supplier identity.
- Recommendation status and quantity.
- Estimated unit and total cost.
- `can_create_draft_po`.
- Hard blockers.
- Advisory warnings.
- Required manager decision for stale-only demand.
- `po_supplier_source`.
- Canonical supplier check result.

## Conversion endpoint changes

`POST /recommendations/{recommendation_id}/convert-to-draft-po` now calls the PO readiness check first. If any blocker exists, the endpoint fails without creating a partial PO.

Successful conversion creates a local draft PO only:

- `status = draft`.
- Supplier comes from `products.supplier_id`.
- PO line stores `product_id`.
- PO line keeps `product_supplier_id = null`.
- Product name, supplier SKU, quantity, unit cost, MOQ, pack size, and lead time are snapshotted from available product/effective input data.
- Recommendation status changes to `converted_to_po`.

The endpoint does not approve, issue, receive, or send a PO to OrderPro.

## Stale-demand safety

Stale-only recommendations remain blocked from PO conversion unless the product has an explicit latest stale-demand decision:

```text
manager_approved_one_time
```

That decision permits only local draft PO conversion after the recommendation is accepted and all other hard blockers pass. It does not globally relax stale-demand policy and does not automatically create a PO.

## Product impact

- Product `3020`: still requires the full safe path: stale review when applicable, manager-approved one-time decision if stale-only, accepted recommendation, then PO readiness passing before draft PO creation.
- Product `7721`: remains monitor/no reorder and should fail PO readiness while forecast action is not `reorder` or quantity is non-positive.
- Product `3001`: remains blocked because missing supplier and missing lead time are hard blockers.

The same rules apply to `3004`, `3021`, `3121`, `3180`, and `3207`: missing pack size alone does not block, but stale-only demand and hard input blockers still do.

## Still not automatic

OP-41 does not:

- Call OrderPro.
- Create OrderPro purchase orders.
- Approve or issue local purchase orders.
- Auto-approve recommendations.
- Mutate existing recommendations except when a user explicitly converts an accepted recommendation.
- Change forecast formulas.
- Change Render configuration.

## Recommended OP-42

Add a manager-facing PO readiness panel in the frontend that calls `GET /recommendations/{recommendation_id}/po-readiness`, disables unsafe conversion actions, and displays blockers before the user attempts draft PO creation.
