# OP-30 Supplier Source of Truth

## Canonical Rule

OrderPro remains the upstream source of truth for products and suppliers. Inside Purchasing AI, the canonical supplier assignment for production purchasing flows is:

1. `products.supplier_id`, joined to `suppliers.id`
2. OrderPro supplier identity fields only when resolving or importing into local `suppliers`
3. legacy product supplier fields only as migration/review evidence
4. `product_suppliers` rows only as legacy review/diagnostic mappings
5. supplier name text only as display/debug fallback, not production identity

Business rule: one product has one active supplier. After supplier identity has been resolved, Forecast, Forecast Readiness, Supplier Forecast, Recommendations, and Purchase Order workflows should use `products.supplier_id` for production behavior.

## Files Inspected

Models:

- `app/models/product.py`
- `app/models/supplier.py`
- `app/models/product_supplier.py`
- `app/models/product_master_item.py`
- `app/models/product_supplier_assignment_review.py`
- `app/models/recommendation.py`
- `app/models/purchase_order.py`
- `app/models/orderpro_purchase_order.py`

Services and routes:

- `app/services/forecasting.py`
- `app/services/forecast_input_reconciliation.py`
- `app/services/seasonality_backtesting.py`
- `app/services/purchase_order_drafting.py`
- `app/services/recommendations.py`
- `app/services/orderpro_sync_planner.py`
- `app/services/supplier_assignment_review.py`
- `app/services/manual_supplier_cleanup.py`
- `app/services/product_supplier_sync.py`
- `app/services/direct_supplier_repair.py`
- `app/services/orderpro_product_supplier_export.py`
- `app/routes/products.py`
- `app/routes/suppliers.py`
- `app/routes/product_suppliers.py`
- `app/routes/purchase_orders.py`
- `app/routes/recommendations.py`
- `app/routes/forecast_readiness.py`
- `app/routes/forecast_reconciliation.py`
- `app/routes/manual_supplier_cleanup.py`
- `app/routes/supplier_assignment_review.py`

Frontend/API surfaces:

- `frontend/src/api.ts`
- `frontend/src/App.tsx`
- `frontend/src/productDisplay.ts`

## Endpoint And Service Audit

| Area / service | Current supplier identity field | Fallback behavior | Risk | Canonical agreement | Recommended fix |
| --- | --- | --- | --- | --- | --- |
| Product model | `Product.supplier_id` / `Product.supplier_record` | Legacy `Product.supplier` text remains on the row | Low | Yes | Keep `supplier_id` as the only production assignment. |
| OrderPro supplier sync | OrderPro supplier `id`, `code`, and name mapped to `suppliers` | Name match is last resort when stronger identifiers are missing | Low after OP-30 | Yes | Keep normalized matching and conflict tests. |
| OrderPro product sync/import | CSV supplier code maps to local `Supplier`, then writes `products.supplier_id` | Missing supplier code leaves existing/empty assignment unchanged by planner rules | Low after OP-30 | Yes | Continue assigning through `products.supplier_id`. |
| Product list/detail API | Main supplier display is from `Product.supplier_record`; some fields can expose legacy names/mappings | `preferred_supplier` can surface `product_suppliers` or legacy text for display | Medium | Partial | Label legacy display fields as diagnostic in a later frontend/API cleanup. |
| Forecast Readiness | Product readiness primarily checks `products.supplier_id` | Assignment review suggestions can be based on legacy evidence | Low/Medium | Mostly | Keep suggestions diagnostic; do not treat legacy evidence as production supplier assignment. |
| Forecast endpoint | `resolve_supplier_context` prefers `products.supplier_id` | Legacy product supplier text can create supplier context when no `supplier_id` exists | Medium/High | Partial | OP-31 should remove or explicitly quarantine legacy fallback from production forecast eligibility. |
| Supplier Forecast | Queries products by `Product.supplier_id == supplier_id` | None observed for production query | Low | Yes | No OP-30 code change needed. |
| Recommendations | Recommendation creation uses `product.supplier_id` in main paths | Some legacy supplier text and `ProductSupplier` conversion paths remain | High | Partial | OP-31 should align recommendation eligibility and PO conversion on `products.supplier_id`. |
| Purchase order drafting | Product-line drafting validates `Product.supplier_id` | Legacy product-supplier PO line route remains for older workflow | Medium | Partial | Keep legacy route stable, but migrate future behavior to product `supplier_id`. |
| ProductSupplier API/pages | `product_suppliers.product_id` and preferred mappings | Preferred supplier rows can look operational | Medium | No, legacy only | Keep for diagnostics/review; relabel and reduce production coupling in later OP. |
| Supplier Assignment Review / Cleanup | Writes confirmed choices to `products.supplier_id` | Uses legacy mappings/master items as evidence | Low | Yes | Keep as migration/review tooling. |
| ProductMasterItem and direct repair | Legacy supplier fields used as evidence | Repair can promote evidence to `products.supplier_id` | Medium | Partial | Keep migration-only posture and require explicit repair/review. |
| OrderPro PO import/inbound | Local joins use product and supplier IDs after sync | Depends on upstream sync quality | Low | Yes | No OP-30 change needed. |

## Inconsistencies Found

- `product_suppliers` still has user-facing API/page behavior that can appear to define the active supplier. It should be treated as legacy review data unless a future OP explicitly repurposes it.
- `Product.supplier` legacy text can still be used by forecast/recommendation context in limited paths. That is useful for migration diagnostics but should not be production supplier truth.
- Recommendation conversion still has legacy `ProductSupplier` coupling in older workflows.
- Product list/detail display may expose legacy supplier labels next to canonical supplier fields, which can confuse users when the values disagree.
- Supplier matching during OrderPro sync needed consistent normalization for OrderPro supplier IDs/codes/names. OP-30 applies this minimal safe fix.

## Files Changed

- `app/services/supplier_identity.py`
- `app/services/orderpro_sync_planner.py`
- `app/models/product_supplier.py`
- `app/models/product_master_item.py`
- `tests/test_supplier_identity.py`
- `tests/test_orderpro_sync_planner.py`
- `notes/op30_supplier_source_of_truth.md`

## Minimal Safe Alignment Applied

- Added `app/services/supplier_identity.py` to document the supplier source-of-truth priority and provide small, reusable normalization/resolution utilities.
- Normalized supplier OrderPro IDs, supplier codes, and supplier names in OrderPro supplier and product sync planning/application paths.
- Added conflict behavior for supplier identity resolution so stronger identifiers cannot silently disagree.
- Documented `ProductSupplier` as legacy supplier mapping evidence rather than the production active supplier.
- Documented `ProductMasterItem` supplier fields as migration and diagnostic evidence.

No broad Forecast, Recommendation, Supplier Forecast, or Purchase Order refactor was performed in OP-30.

## Tests Added Or Updated

- `tests/test_supplier_identity.py`
  - source-of-truth priority is documented in code
  - supplier code/name normalization
  - canonical display prefers `products.supplier_id` relationship over legacy text
  - legacy supplier text is display-only when `supplier_id` is missing
  - conflicting OrderPro ID/code identifiers do not silently match
  - name fallback is allowed only when stronger identifiers are missing
- `tests/test_orderpro_sync_planner.py`
  - product planning normalizes supplier codes before assignment
  - supplier planning matches existing suppliers by normalized code

## Validation

Targeted backend validation:

```text
218 passed
```

Command:

```powershell
$env:DEBUG='false'; .\.venv\Scripts\python.exe -m pytest tests\test_supplier_identity.py tests\test_orderpro_sync_planner.py tests\test_forecasting_supplier_resolution.py tests\test_forecast_response_supplier_context.py tests\test_forecast_input_reconciliation.py tests\test_recommendations.py tests\test_purchase_order_workflow.py tests\test_supplier_assignment_review.py tests\test_manual_supplier_cleanup.py tests\test_product_supplier_api.py -v
```

Full backend validation:

```text
463 passed
```

Command:

```powershell
$env:DEBUG='false'; .\.venv\Scripts\python.exe -m pytest -q
```

No frontend files were changed for OP-30, so frontend tests were not required for this OP.

## Remaining Risks

- Forecast still contains legacy supplier text fallback behavior that can produce supplier context without `products.supplier_id`.
- Recommendations still contain legacy reviewable paths and conversion behavior tied to supplier text or `ProductSupplier`.
- Product Supplier Mapping/Cleanup UI and APIs may still look like operational supplier assignment even though they are now defined as legacy diagnostics.
- Duplicate or conflicting supplier codes/names still require review; normalization prevents casing/spacing misses but does not decide business conflicts.
- Existing OP-29 and frontend worktree changes are intentionally left separate from OP-30.

## Recommended Next OP

OP-31 should align Forecast and Recommendations supplier resolution to the finalized source-of-truth rule:

- make `products.supplier_id` the only production supplier source for forecast/recommendation readiness
- remove or explicitly mark legacy supplier text fallback as diagnostic-only
- ensure recommendation-to-PO conversion uses product `supplier_id` rather than `ProductSupplier`
- add regressions proving legacy `product_suppliers` or supplier names cannot make a product production-ready when `products.supplier_id` is missing
- keep Supplier Mapping/Cleanup pages as review tools unless intentionally redesigned
