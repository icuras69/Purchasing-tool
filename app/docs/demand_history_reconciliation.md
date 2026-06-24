# Demand History Reconciliation

OP-24A adds a local-only workflow for importing reviewed historical demand into the existing `usage_history` table. It does not call OrderPro, change forecast formulas, alter supplier assignments, or modify purchase orders.

## Source Files

The import service supports CSV and XLSX files. For workbooks, the default is intentionally conservative: only sheets whose names look like years, such as `2022`, `2023`, `2024`, and `2025`, are imported. Lookup, customer, supplier, and control sheets are skipped unless the user explicitly opts into them.

The workbook inspector reports:

- sheet names
- rows scanned per sheet
- detected header row
- detected columns
- whether the sheet was included as sales data
- skip reason for excluded sheets

It accepts common historical sales columns case-insensitively, including the legacy sales workbook shape:

- `Name`
- `Barcode`
- `Description`
- `Batch`
- `Invoice`
- `Date`
- `Price`
- `Quantity`
- `Gross`
- `Nett`
- `Code`
- `Purchase Order`

The runtime inspection report lists the exact detected and mapped columns for each file. Required fields are:

- a sale/demand date
- a quantity
- at least one product identifier: local product ID, OrderPro SKU, SKU/code, barcode, product name, or legacy/Xero-style description/name

## Matching Precedence

Rows are matched deterministically only. No fuzzy matching is used.

1. Exact local `products.id`
2. Exact `products.orderpro_sku`
3. Exact current product barcode when the barcode maps to one product
4. Exact sales `Code` through the safe alias index
5. Exact sales `Barcode` through the safe alias index
6. Exact Product Lookup bridge match, when the lookup row maps to one current product
7. Exact unique product name/description
8. Exact unique legacy/canonical product description
9. Unmatched or ambiguous

Before falling back to barcode-only matching, OP-24B adds composite aliases for variant-heavy legacy rows:

- normalized source Barcode + normalized source Description
- normalized source Barcode + normalized source product name
- normalized source Code + normalized source Description
- normalized source Code + normalized source product name

This resolves rows like `UDDERMINT500ML` + `Tenison Udder Mint 500ml` to the exact variant when the shared barcode alone maps to multiple products. If the composite alias also maps to multiple products, the row stays ambiguous.

If `Code` and `Barcode` both match but point to different products, the row is marked ambiguous/conflict and skipped.

Ambiguous matches are skipped and reported for review.

## Product Lookup and Reviewed Mapping Files

The workbook `Product Lookup` sheet is never imported as sales demand by default. When it contains explicit old-to-current product bridge columns, it can contribute safe aliases only if the lookup row resolves to exactly one current product.

The planner also accepts an optional reviewed mapping CSV:

```powershell
.\.venv\Scripts\python.exe scripts\plan_demand_history_import.py --file "PATH_TO_FILE.xlsx" --mapping-file "PATH_TO_REVIEWED_MAPPING.csv" --save-report
```

Expected reviewed mapping columns are:

- `source_code`
- `source_barcode`
- `source_description`
- `product_id`
- `reviewed_by`
- `notes`

The mapping file affects planning and matching only. It never creates products and does not write to the database unless the user later runs the existing demand import with `--apply`.

## Non-Product Service Rows

Obvious fee/service rows such as shipping, delivery, collection, discount, heavy item surcharge, sponsorship, packaging, fulfillment, admin fees, customs, postage, courier/DHL/FedEx charges, logo digitisation, and supply-and-deliver service lines are classified as `excluded_non_inventory`. Rows that initially match a local product can still be excluded when the source row or matched product carries clear service/fee signals. The dry-run reports those separately as `matched_service_rows_excluded` so they can be audited before any apply.

## Validation

The dry-run detects and reports:

- missing product identifiers
- invalid or future dates
- invalid or zero quantities
- duplicate source rows
- rows already present in `usage_history` for the same product/date/source
- unmatched and ambiguous product matches

Negative quantities are preserved as returns. For inserted `usage_history` rows:

- positive quantities go to `qty_used`
- negative quantities go to `qty_returned`
- `net_qty` preserves the signed net demand

## Duplicate Strategy

The importer is idempotent for the dedicated source system `demand_history_import`.

Multiple safe rows for the same product and date are aggregated into one `usage_history` row because the existing table has a unique key on `product_id`, `date`, and `source_system`.

An exact duplicate source row is marked `duplicate` in the reconciliation report. A row that has already been imported for the same product/date/source is also marked `duplicate` and is not inserted again.

## Commands

Dry-run only:

```powershell
.\.venv\Scripts\python.exe scripts\plan_demand_history_import.py --file "PATH_TO_FILE.xlsx" --save-report
```

Dry-run with ambiguity review exports:

```powershell
.\.venv\Scripts\python.exe scripts\plan_demand_history_import.py --file "PATH_TO_FILE.xlsx" --save-report --save-ambiguous-review
```

Dry-run explicit sheet list:

```powershell
.\.venv\Scripts\python.exe scripts\plan_demand_history_import.py --file "PATH_TO_FILE.xlsx" --sheets "2022,2023,2024,2025" --save-report
```

Inspect/import every sheet with a valid sales header:

```powershell
.\.venv\Scripts\python.exe scripts\plan_demand_history_import.py --file "PATH_TO_FILE.xlsx" --all-sheets --save-report
```

Apply reviewed local import:

```powershell
.\.venv\Scripts\python.exe scripts\plan_demand_history_import.py --file "PATH_TO_FILE.xlsx" --apply --reviewed-by "Maged" --save-report
```

Reports are written under:

```text
tmp/demand_history_import_reports/
```

The JSON report contains the workbook inspection, per-sheet summary counts, top ambiguity reasons, grouped ambiguity summaries, top ambiguous samples, and row-level statuses. The CSV reconciliation file contains one row per source row with sheet name, source row number, match status, matched product, reason, source Code, source Barcode, source Description, candidate products for ambiguous rows, parsed date, parsed quantity, and duplicate key.

When `--save-report` is used, an additional `demand_history_excluded_service_rows_<timestamp>.csv` file is written with the matched product, source row, exclusion reason, quantity, and gross revenue for service/fee exclusions.

When `--save-ambiguous-review` is used, two additional files are created:

- `demand_history_ambiguous_review_<timestamp>.csv`
- `demand_history_ambiguous_grouped_<timestamp>.csv`

The grouped file summarizes repeated ambiguity cases by source Code, Barcode, and Description so a reviewer can resolve the highest-impact identifiers first.

## API Routes

All routes use the existing admin authentication dependency and respect `AUTH_ENABLED`.

- `GET /api/demand-history-reconciliation/summary`
- `GET /api/demand-history-reconciliation/products`
- `GET /api/demand-history-reconciliation/products/{product_id}`
- `GET /api/demand-history-reconciliation/export.csv`

The products route supports filters for search, supplier ID, history presence, recent demand, stale demand, sorting, and pagination.

## Coverage CSV

The exported demand coverage CSV uses UTF-8 with BOM. Columns are:

- `product_id`
- `sku`
- `product_name`
- `supplier_id`
- `supplier_code`
- `supplier_name`
- `has_demand_history`
- `demand_row_count`
- `earliest_demand_date`
- `latest_demand_date`
- `months_covered`
- `total_units`
- `units_last_30_days`
- `units_last_90_days`
- `average_monthly_units`
- `return_units`
- `stale_demand`
- `gap_warnings`
- `readiness_status`
- `readiness_score`
- `demand_source`

Text cells are protected from spreadsheet formula injection.

## Frontend

The Demand History tab shows coverage summary cards, import command guidance, product-level coverage filters, detail monthly buckets, and CSV export. It is review-oriented: imports still happen through the CLI so a user can inspect reports before applying.

## OP-25 Roadmap

This task does not change forecast formulas. A later task can use the imported local history to evaluate demand-source precedence, compare OrderPro order history with historical sales files, and decide whether older demand should supplement recent OrderPro demand for specific products.
