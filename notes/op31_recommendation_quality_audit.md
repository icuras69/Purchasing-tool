# OP-31 Recommendation Quality Audit And Forecast Explainability

## Summary

OP-31 adds a read-only recommendation explanation surface and a stored-recommendation audit surface. It also prevents newly generated reorder recommendations from becoming actionable when canonical supplier assignment, demand signal, usable lead time, or a reorder forecast is missing.

No OrderPro sync/API calls were added. No Render configuration was changed. No production database data was changed; manual verification used read-only database queries and ended with transaction rollback.

## Recommendation Logic Location

- Recommendation routes: `app/routes/recommendations.py`
- Recommendation creation/review/conversion service: `app/services/recommendations.py`
- Forecast formula and demand/supplier/stock context: `app/services/forecasting.py`
- OrderPro demand calculation: `app/services/orderpro_demand.py`
- Forecast input readiness/effective lead time/MOQ/cost: `app/services/forecast_input_reconciliation.py`
- Forecast readiness APIs: `app/routes/forecast_readiness.py`, `app/routes/forecast_reconciliation.py`
- Frontend recommendation list/detail: `frontend/src/App.tsx`
- Frontend API/types: `frontend/src/api.ts`, `frontend/src/types.ts`
- Existing recommendation tests: `tests/test_recommendations.py`

## Current Formula And Inputs

Forecast generation happens in `build_forecast(db, product)`.

Inputs used:

- Product identity: local `products.id`; OrderPro fields are displayed/snapshotted where present.
- Supplier: `products.supplier_id` joined to `suppliers`; legacy supplier text can still exist in forecast context, but OP-31 blocks new recommendations without canonical `products.supplier_id`.
- Demand: OrderPro orders first when OrderPro product identity/history exists; otherwise legacy `usage_history`.
- Stock: `products.current_stock`, with inventory positions only used as source context.
- Inbound stock: open/approved inbound purchase order lines reduce reorder quantity.
- Lead time: effective forecast input resolution uses product lead time first, then supplier lead time, then legacy `ProductSupplier` lead time as low-confidence input, otherwise missing.
- MOQ: product `min_order_qty` when positive, otherwise business default `1`.
- Pack size: product pack size when available; otherwise no order multiple is applied.
- Safety stock: product safety stock when present, otherwise business default `0`.
- Cost: product cost first, then recent OrderPro/local purchase order line cost, otherwise missing.

Demand window:

- OrderPro demand uses `settings.forecast_demand_lookback_days`, default `90`.
- OrderPro shipped statuses default to `shipped`.
- OrderPro open demand statuses default to `confirmed`, `packed`, `backorder`.
- Legacy `usage_history` currently uses all rows for the product, with no lookback cutoff.

Stock and reorder calculation:

- `effective_available_stock = max(current_stock - open_demand, 0)`
- `net_available_stock = current_stock - open_demand`
- `effective_available_stock_for_reorder = current_stock + incoming_qty - open_demand`
- `projected_lead_time_demand = avg_daily_usage * lead_time_days`
- `reorder_point = projected_lead_time_demand + safety_stock`
- `total_required_stock = projected_lead_time_demand + open_demand + safety_stock`
- raw reorder need is `max(total_required_stock - current_stock - incoming_qty, 0)`
- positive reorder quantities are rounded to integer and then pack size when available
- positive reorder quantities are raised to MOQ when below MOQ

Blocked/monitor behavior observed:

- Forecast returns `monitor` when no usage history exists and no raw shortfall is created.
- Forecast returns `needs_supplier_mapping` when demand exists but no usable lead time exists.
- OP-31 explanation marks missing supplier, no demand/open demand, missing lead time, missing stock, and non-inventory products as blocked for recommendation trust.
- OP-31 recommendation creation now rejects blocked/non-actionable products before writing a recommendation row.

Stale and negative demand:

- Existing forecast does not exclude stale legacy `usage_history`; OP-31 audit warns when last demand is older than 180 days and no open demand is present.
- OrderPro negative shipped quantities are excluded from demand.
- Legacy `usage_history` demand currently sums `qty_used`; OP-31 audit flags rows with negative `qty_used`, negative `net_qty`, or positive `qty_returned`.

## Endpoints Added

### `GET /recommendations/explain?product_id={id}`

Read-only product explanation endpoint. It returns:

- product ID/name
- supplier ID/name/source
- stock and inventory source
- demand source, demand row count, last demand date, recent demand, monthly average demand
- lead time and source
- days of cover
- MOQ/source
- inbound stock
- recommended action and quantity
- reason, reasons, blockers, warnings, confidence, readiness status
- suspicious issues
- forecast snapshot

### `GET /recommendations/audit?limit=500`

Read-only stored recommendation audit. It evaluates existing recommendation rows and flags suspicious cases without deleting or mutating data.

Summary fields:

- recommendations evaluated
- suspicious recommendation count
- issue counts
- limit used

Item fields:

- recommendation/product/supplier identity
- stored status and quantity
- explanation status
- forecast recommended action
- blockers
- warnings
- suspicious issues

## Suspicious Recommendation Checks Added

The audit flags:

- actionable recommendation missing supplier
- actionable recommendation with no demand history/open demand
- actionable recommendation with stale demand only
- actionable recommendation with non-positive quantity
- recommended quantity less than MOQ
- actionable recommendation where forecast action is not reorder
- recommendation that appears to have enough stock without a clear shortfall

New recommendation creation now rejects:

- missing canonical supplier assignment
- missing usable supplier lead time
- missing demand history/open demand
- forecast status that is not actionable reorder

Existing suspicious recommendation rows are not deleted or changed.

## Frontend Detail Changes

The existing Recommendation Details panel was extended, not redesigned.

Added visible fields:

- Product ID
- product name
- supplier
- current stock
- demand rows
- recent demand
- average monthly demand
- lead time
- days of cover
- blockers
- warnings

The panel still shows existing supplier and forecast snapshots, reason, status, quantity, and advisory safety messaging.

## Demo Product Verification

Read-only explanation checks were run for the requested product IDs on July 9, 2026.

| Product ID | Product | Supplier | Status | Demand rows | Last demand | Avg monthly demand | Stock | Lead time | Recommended qty | Blockers | Warnings |
| --- | --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |
| 3020 | Blo i200 Single Motor Blower - UK Plug | Christies | actionable | 2 | 2025-06-03 | 60.88 | 0 | 3 | 6 | none | stale demand, missing pack size |
| 3004 | Cow Start Bolus 4 x 2 pack | Acravet Ltd | actionable | 1 | 2025-07-02 | 30.44 | 0 | 2 | 2 | none | stale demand, missing pack size |
| 3021 | Blo i400 Dual Motor Blower - UK Plug | Christies | actionable | 10 | 2025-11-03 | 1.22 | 0 | 3 | 1 | none | stale demand, missing pack size |
| 3121 | Heiniger Xperience Clipper | Mullinahone | actionable | 1 | 2024-03-19 | 30.44 | 0 | 7 | 7 | none | stale demand, missing pack size |
| 3180 | Uddermint - Teisen - 2.5Litre | Cleanline | actionable | 5 | 2025-01-29 | 1.83 | 0 | 2 | 1 | none | stale demand, missing pack size |
| 3207 | Osmonds Bactakil 55 Spray | Osmonds | actionable | 7 | 2025-10-03 | 0.61 | 0 | 21 | 1 | none | stale demand, missing pack size |
| 7721 | Plastic Curry Comb - Blue | Mullinahone | monitor | 16 | 2026-06-04 | 12.18 | 20 | 7 | 0 | none | missing pack size |

Interpretation:

- Products `3020`, `3004`, `3021`, `3121`, `3180`, and `3207` are explainable reorder candidates because stock is zero and supplier/lead time exists.
- All six actionable examples carry stale-demand warnings because the last demand is older than 180 days as of July 9, 2026.
- Product `7721` is not recommended because current stock is sufficient based on recent average daily usage.

## Example Explanation: Product 3020

```json
{
  "product_id": 3020,
  "product_name": "Blo i200 Single Motor Blower - UK Plug",
  "supplier_name": "Christies",
  "current_stock": 0.0,
  "demand_rows": 2,
  "last_demand_date": "2025-06-03",
  "monthly_average_demand": 60.88,
  "lead_time_days": 3,
  "days_of_cover": 0.0,
  "recommended_quantity": 6.0,
  "status": "actionable",
  "blockers": [],
  "warnings": [
    "Stale demand only; last demand is older than 180 days",
    "Missing pack size"
  ],
  "reason": "Projected lead-time demand is 6.0 units and reorder point is 6.0."
}
```

## Example Blocked Explanation

Read-only scan found product `3001`.

```json
{
  "product_id": 3001,
  "product_name": "Noromectin 7l",
  "supplier_name": null,
  "current_stock": 0.0,
  "demand_rows": 1,
  "last_demand_date": "2024-12-20",
  "lead_time_days": null,
  "recommended_quantity": 0.0,
  "status": "blocked",
  "blockers": [
    "Missing supplier",
    "Missing lead time"
  ],
  "warnings": [
    "Stale demand only; last demand is older than 180 days",
    "Missing cost",
    "Missing pack size"
  ],
  "reason": "Demand exists for this product, but there is no usable supplier lead time yet. Map the product to a supplier with a valid lead time before generating a purchase recommendation."
}
```

## Files Changed

- `app/services/recommendation_audit.py`
- `app/services/recommendations.py`
- `app/routes/recommendations.py`
- `frontend/src/App.tsx`
- `frontend/src/App.test.tsx`
- `tests/test_direct_supplier_repair.py`
- `tests/test_recommendations.py`
- `notes/op31_recommendation_quality_audit.md`

## Tests

Targeted backend:

```text
94 passed
```

Command:

```powershell
$env:DEBUG='false'; .\.venv\Scripts\python.exe -m pytest tests\test_recommendations.py tests\test_forecasting_supplier_resolution.py tests\test_forecast_response_supplier_context.py tests\test_purchase_order_workflow.py -v
```

Full backend:

```text
467 passed
```

Command:

```powershell
$env:PYTHONPATH=(Get-Location).Path; $env:AUTH_ENABLED='true'; $env:DEBUG='true'; $env:ADMIN_EMAIL='admin@example.com'; .\.venv\Scripts\python.exe -m pytest -v
```

Frontend tests:

```text
3 files passed, 140 tests passed
```

Command:

```powershell
Remove-Item Env:VITE_AUTH_ENABLED -ErrorAction SilentlyContinue; $env:VITE_API_BASE_URL='http://127.0.0.1:8000'; npm.cmd run test -- --run
```

Frontend build:

```text
tsc -b && vite build passed
```

Command:

```powershell
Remove-Item Env:VITE_AUTH_ENABLED -ErrorAction SilentlyContinue; $env:VITE_API_BASE_URL='http://127.0.0.1:8000'; npm.cmd run build
```

## Remaining Risks

- Forecast itself still contains legacy supplier text context for non-recommendation uses; OP-31 blocks new recommendations from using it as actionable supplier truth.
- Legacy `usage_history` still has no lookback cutoff in the forecast formula. OP-31 warns on stale demand but does not change demand math.
- Legacy `usage_history` uses `qty_used` in the forecast calculation. OP-31 flags returns/negative rows, but does not change the historical demand formula.
- Missing pack size is common in demo products. The formula can still recommend integer quantities without pack multiple rounding.
- Recommendation-to-PO conversion still waits for the purchase order refactor and does not automatically create purchase orders.

## Recommended Next OP

OP-32 should decide whether stale historical demand should remain advisory, require a freshness threshold, or use a weighted/recent demand window for recommendation creation. It should also decide whether legacy `usage_history` demand should use `net_qty` instead of `qty_used` now that returns are visible.
