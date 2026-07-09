# OP-29 Product Identity Standardization Audit

## Canonical Product Identity Priority

Product identity should be resolved in this order:

1. OrderPro product ID, when available.
2. SKU / product code.
3. Barcode.
4. Normalized product name/title only as a fallback.
5. Internal database `products.id` only for local joins after identity resolution.

`usage_history.product_id`, `inventory_positions.product_id`, `orderpro_order_items.product_id`, recommendation rows, and purchase-order lines should reference local `products.id` only after an importer, sync, route, or explicit user action has resolved identity using stronger external identifiers.

## Files Inspected

Models:

- `app/models/product.py`
- `app/models/usage_history.py`
- `app/models/sales_history_raw.py`
- `app/models/inventory_position.py`
- `app/models/orderpro_order.py`
- `app/models/orderpro_purchase_order.py`
- `app/models/recommendation.py`
- `app/models/purchase_order.py`
- `app/models/product_master_item.py`
- `app/models/product_supplier.py`
- `app/models/product_historical_link.py`
- Alembic source-of-truth/product identity migrations.

Services and routes:

- `app/services/demand_history_reconciliation.py`
- `app/services/forecasting.py`
- `app/services/orderpro_demand.py`
- `app/services/orderpro_sync_planner.py`
- `app/services/inventory_sync.py`
- `app/services/forecast_input_reconciliation.py`
- `app/services/seasonality_backtesting.py`
- `app/services/recommendations.py`
- `app/services/purchase_order_drafting.py`
- `app/services/purchase_order_export.py`
- `app/services/inbound_stock.py`
- `app/services/product_search.py`
- `app/services/manual_supplier_cleanup.py`
- `app/routes/products.py`
- `app/routes/demand_history_reconciliation.py`
- `app/routes/forecast_readiness.py`
- `app/routes/recommendations.py`
- `app/routes/purchase_orders.py`
- `app/routes/product_suppliers.py`

Frontend API usage reviewed:

- `frontend/src/api.ts`
- `frontend/src/App.tsx`
- `frontend/src/productDisplay.ts`

## Identity Field Inventory

| Field | Location | Meaning |
| --- | --- | --- |
| `products.id` | Core product table and local FKs | Local database identity after resolution. |
| `products.orderpro_id` | Product table, OrderPro sync/import | Preferred external product identity. Unique and indexed. |
| `products.orderpro_sku` | Product table, sync/search/exports | SKU/product code fallback. Unique and indexed. |
| `products.source_key` | Product table, legacy/imported records | Legacy source key or OrderPro SKU mirror in sync. |
| `products.barcode` | Product table, demand import/search/export | Barcode fallback, not unique. |
| `products.name`, `description`, `canonical_description` | Product table, demand import/search | Human-readable fallback, risky if used before stronger IDs. |
| `sales_history_raw.product_id` | Raw historical demand rows | Optional local product link for audit/import evidence. |
| `usage_history.product_id` | Forecast demand history | Local product FK after demand import/reconciliation. |
| `inventory_positions.product_id` | Inventory sync/cache | Local product FK after OrderPro ID/SKU resolution. |
| `inventory_positions.orderpro_product_id` | Inventory cache | External OrderPro product ID evidence. |
| `orderpro_order_items.product_id` | OrderPro order mirror | Local product FK after OrderPro ID/SKU resolution. |
| `orderpro_order_items.orderpro_product_id`, `sku`, `name` | OrderPro order mirror | External item evidence. |
| `recommendations.product_id` | Recommendation table | Local product FK after forecast/recommendation route uses `products.id`. |
| `purchase_order_lines.product_id` | PO lines | Local product FK after route/drafting validates product. |
| `product_master_items.sku`, `product_id` | Legacy master item mapping | Legacy SKU-to-local-product evidence. |
| `product_suppliers.product_id`, `supplier_sku` | Legacy supplier mapping | Supplier mapping evidence, not canonical product identity. |

## Matching Path Audit

| Area / endpoint | Current identity field used | Fallback behavior | Risk | Canonical agreement | Recommended fix |
| --- | --- | --- | --- | --- | --- |
| Demand History import/reconciliation | Explicit imported `product_id`, then `orderpro_sku`, then reviewed mapping / barcode / code / lookup aliases / name | Ambiguous barcode/name/code matches are skipped for review. Name is late fallback. | Medium | Mostly yes, except explicit local product ID can precede external IDs when supplied by a trusted reviewed file. | Keep behavior. Future OP can route normalization through `product_identity.py` after more regression tests. |
| Demand History list endpoint | Local `products.id` rows, `orderpro_sku`/barcode/supplier SKU search, then name/supplier search | Product ID exact search wins. Summary uses aggregate `usage_history` from OP-26D/OP-28. | Low | Yes after import resolution. | No code change in OP-29. |
| Demand History summary endpoint | Aggregate SQL over `usage_history.product_id` where `source_system = 'demand_history_import'` | None. Counts local FK rows already resolved by import. | Low | Yes. | No code change in OP-29. |
| Forecast Readiness | OrderPro catalogue filter, local `products.id`; demand evidence via OrderPro order items and confirmed historical links | Search exact product ID, SKU/barcode/supplier SKU, then name/supplier. | Low | Yes after resolution. | No code change in OP-29. |
| Forecast endpoint | Route accepts local `products.id`; forecast reads `OrderProOrderItem.product_id` first for OrderPro demand, then `UsageHistory.product_id` fallback | Falls back from OrderPro demand to usage history when no usable OrderPro demand exists. | Low | Yes. | No code change in OP-29. |
| Supplier Forecast | Supplier ID selects `Product.supplier_id`; each forecast uses local product ID | No product identity resolution in supplier forecast itself. | Low | Yes after product sync. | Supplier resolution intentionally unchanged. |
| Recommendations | Route accepts local `products.id`; recommendation stores local `product_id` | Forecast snapshot includes OrderPro SKU and product identity evidence. | Low | Yes. | Recommendation formula intentionally unchanged. |
| Purchase Order generation | Product route accepts local `products.id`; line stores local `product_id`; CSV exports local ID plus OrderPro ID/SKU/barcode | Product supplier validation uses `Product.supplier_id`. | Low | Yes after route selection. | PO workflow intentionally unchanged. |
| OrderPro product sync/import | Matched by `products.orderpro_id`, then `products.orderpro_sku` | CSV supplier rows keyed by SKU. | Medium before OP-29 due casing/spacing misses | Yes after OP-29 | Normalize OrderPro ID/SKU lookup keys. Done. |
| OrderPro inventory sync/import | Matched by OrderPro product ID, then nested SKU | Planned products also considered during dry run. | Medium before OP-29 due casing/spacing misses | Yes after OP-29 | Normalize ID/SKU lookup keys. Done. |
| OrderPro order sync/import | Matched by OrderPro product ID, then item SKU | Missing matches are reported and skipped as local product links. | Medium before OP-29 due casing/spacing misses | Yes after OP-29 | Normalize ID/SKU lookup keys. Done. |
| Legacy inventory provider sync | Previously matched only `ProductMasterItem.sku -> product_id` | No direct fallback to `products.orderpro_sku`. | Medium before OP-29 | Partially | Keep master-item link first, then fallback to normalized `products.orderpro_sku`. Done. |
| Frontend product search/detail views | Calls backend APIs with local product IDs for detail/forecast/recommendation/PO actions | Search terms sent as query strings. | Low | Yes, backend enforces behavior. | No frontend change in OP-29. Existing frontend working-tree edits were left untouched. |

## Inconsistencies Found

1. OrderPro sync lookups used raw SKU strings in several places. This could miss an existing local product if an external payload sent `sku-1`, ` SKU-1 `, or a differently cased product CSV key. Fixed by normalizing SKU/code lookup keys centrally.
2. The older `inventory_sync.py` provider path depended only on legacy `ProductMasterItem.sku -> product_id`. If no master item existed, a valid OrderPro product with the same SKU was skipped. Fixed by preserving master-item precedence and adding a normalized `products.orderpro_sku` fallback.
3. Search endpoints use similar but duplicated exact-ID, exact-SKU/barcode, then partial-name logic. Tests already protect the numeric product ID behavior. This remains a future consolidation risk, not a bug fixed here.
4. Demand-history reconciliation has its own normalization helpers and a richer ambiguity model. It agrees with the priority in practice, but should not be mechanically rewired until a future OP can preserve all demand import edge cases.

## Files Changed

- `app/services/product_identity.py`
- `app/services/orderpro_sync_planner.py`
- `app/services/inventory_sync.py`
- `tests/test_product_identity.py`
- `tests/test_inventory_sync.py`
- `tests/test_orderpro_sync_planner.py`
- `notes/op29_product_identity_standardization.md`

Observed pre-existing changes not made by OP-29 and left untouched:

- `app/services/demand_history_reconciliation.py`
- `tests/test_demand_history_reconciliation.py`
- `frontend/src/App.tsx`
- `frontend/src/App.test.tsx`

## Tests Added / Updated

- Added product identity helper tests for:
  - canonical priority documentation,
  - SKU/code normalization,
  - barcode normalization and placeholder rejection,
  - name fallback only when stronger identifiers are missing,
  - conflict detection when stronger identifiers point to different products,
  - ambiguous barcode detection.
- Added inventory provider regression test for normalized `products.orderpro_sku` fallback.
- Added OrderPro order and inventory sync planner regression tests for normalized SKU fallback.

## Validation

Targeted backend tests:

```text
91 passed, 53 warnings
```

Full backend pytest:

```text
455 passed, 704 warnings
```

Frontend tests were not run because OP-29 did not change frontend files. Existing frontend modifications were already present in the worktree and were kept separate.

## Remaining Risks

- Product search normalization is still duplicated across product, supplier mapping, demand history, forecast readiness, and cleanup paths.
- Demand-history reconciliation still owns separate normalization helpers because it has more specialized ambiguity handling.
- `products.id` is still exposed as the operational route parameter for many endpoints. This is acceptable after identity resolution, but user-facing flows should keep displaying OrderPro ID/SKU where useful.
- Barcode is not unique in the product table; barcode matching must continue to treat duplicates as ambiguous.
- Supplier resolution, recommendation formula, and purchase-order workflow were intentionally not refactored in this OP.

## Recommended Next OP

OP-30 should consolidate read/search-only product identity behavior across backend endpoints. Suggested scope:

- Reuse `product_identity.py` for shared exact identifier normalization in product, forecast readiness, demand coverage, manual cleanup, and product supplier search.
- Keep endpoint semantics unchanged: exact local product ID first for explicit user search, exact SKU/barcode next, partial name/supplier last.
- Add cross-endpoint tests for casing/spacing and barcode placeholders.
- Do not change supplier resolution or recommendation/PO formulas unless a direct identity bug is found.
