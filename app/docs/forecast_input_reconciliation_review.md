# Forecast Input Reconciliation Review

Forecast input reconciliation is a read-only review layer for the current OrderPro product catalogue. It explains whether a product has the deterministic inputs needed for useful forecasting and purchasing review.

This workflow does not call OrderPro, does not change supplier assignments, does not change forecast formulas, and does not activate seasonality adjustments.

## API Routes

- `GET /api/forecast-reconciliation/summary`
- `GET /api/forecast-reconciliation/products`
- `GET /api/forecast-reconciliation/products/{product_id}`
- `GET /api/forecast-reconciliation/export.csv`

All routes use the existing admin dependency. When `AUTH_ENABLED=false`, the centralized authentication bypass applies. When `AUTH_ENABLED=true`, the routes require a valid admin bearer token.

## Readiness Categories

- `ready`: supplier, stock, product identity, shipped demand history, and the major purchasing inputs are present with no reconciliation warnings.
- `partially_ready`: no blocking issue exists, but one or more useful inputs are missing or fallback-based.
- `blocked`: a critical input is missing, such as supplier assignment, product identity, or current stock.
- `monitor_only`: no blocking issue exists, but there is no shipped demand history or open customer demand signal.

The score is calculated in `evaluate_product_readiness` from deterministic input flags:

- supplier assignment
- lead time
- current stock
- shipped demand history
- cost
- pack size
- product identifier
- MOQ
- safety stock

The review also records source labels for supplier, lead time, stock, demand, cost, pack size, and seasonality.

## CSV Export

The CSV export uses UTF-8 with BOM and one row per product. Text fields are sanitized to reduce spreadsheet formula-injection risk.

Columns:

- `product_id`
- `sku`
- `product_name`
- `supplier_id`
- `supplier_code`
- `supplier_name`
- `current_stock`
- `demand_history_status`
- `lead_time`
- `cost`
- `pack_size`
- `readiness_score`
- `readiness_status`
- `missing_inputs`
- `warnings`
- `demand_source`
- `supplier_source`
- `stock_source`
- `cost_source`
- `recommendation_status`
- `recommended_quantity`

## Frontend Review

The Forecast Readiness tab displays summary cards, filters, a paginated table, product detail, and CSV export. It links blocked supplier cases to the Supplier Cleanup page and keeps the standard Forecast page available for deeper product review.

## OP-25 Roadmap Note

Scheduled OrderPro read synchronization should be handled in a later task. The safest future plan is:

- products, suppliers, and derived warehouses every 30 minutes;
- inventory every 15-30 minutes;
- orders and purchase orders on a separate cadence;
- no overlapping runs;
- retry/backoff and last-success tracking;
- a manual "Sync Now" action;
- preserve local manual supplier cleanup assignments when OrderPro still has no supplier assignment;
- no OrderPro writes unless a separate approved task explicitly adds them.

