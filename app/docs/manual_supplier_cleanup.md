# Manual Supplier Cleanup

OrderPro is the source of truth, but the OrderPro product API and prior product exports do not expose deterministic supplier evidence for every current product. After automated recovery, the remaining missing-supplier products need business review.

This workflow exports those products into a review file, then imports reviewed supplier decisions back into local `products.supplier_id` and `product_supplier_assignment_reviews`.

It is local-only. It does not write to OrderPro.

## Export Workflow

Export all remaining missing-supplier products:

```powershell
..venv\Scripts\python.exe scripts\export_missing_supplier_cleanup.py --format csv --save-report
```

Export only operational priority rows:

```powershell
..venv\Scripts\python.exe scripts\export_missing_supplier_cleanup.py --only-priority --format csv --save-report
```

The export includes product identity, stock/demand/readiness signals, any existing supplier suggestion, and blank review fields:

- `reviewed_supplier_id`
- `reviewed_supplier_code`
- `reviewed_supplier_name`
- `review_note`

Business users should fill at least one reviewed supplier identifier. Supplier name matching is exact and must be unique.

## Priority Scoring

Priority is advisory only. It never assigns a supplier automatically.

The score increases when a product has:

- open customer demand;
- stock on hand;
- historical demand;
- known cost;
- usable seasonality;
- an existing supplier suggestion;
- no blocking forecast issue other than missing supplier.

Suggested actions:

- `review_supplier`
- `confirm_existing_suggestion`
- `needs_business_input`
- `ignore_until_needed`

## Import Workflow

Dry-run a reviewed file:

```powershell
..venv\Scripts\python.exe scripts\import_missing_supplier_cleanup.py --file "PATH_TO_REVIEWED_FILE.csv" --dry-run --save-report
```

Apply reviewed decisions locally:

```powershell
..venv\Scripts\python.exe scripts\import_missing_supplier_cleanup.py --file "PATH_TO_REVIEWED_FILE.csv" --apply --reviewed-by "Maged" --save-report
```

## Supplier Matching

Matching precedence:

1. `reviewed_supplier_id` exactly matches local `suppliers.id`.
2. `reviewed_supplier_code` exactly matches local `suppliers.orderpro_code`.
3. `reviewed_supplier_name` exactly matches one unique normalized supplier name.

The importer does not fuzzy-match, infer from product name/category, or create suppliers.

Rows are skipped when:

- no reviewed supplier field is filled;
- the supplier does not exist locally;
- supplier name is ambiguous;
- the product already has a different supplier;
- the product cannot be found.

If the product already has the same supplier, the row is treated as idempotent and skipped without changing data.

## Forecast Impact

Confirmed cleanup rows update local `products.supplier_id`. Once confirmed, the existing forecast readiness, supplier forecast, and draft PO generation logic can use that supplier assignment.

Unreviewed export rows and dry-run results do not affect forecasting or purchase orders.

## Safety Rules

- No OrderPro write endpoints are called.
- No supplier is inferred from names/categories.
- No fuzzy matching is used.
- No purchase orders are created, approved, issued, received, cancelled, or edited.
- Seasonality remains advisory and does not alter order quantities.

## Local Web Review UI

Task OP-22B adds a local `Supplier Cleanup` page in the frontend and protected API routes under
`/api/manual-supplier-cleanup`.

The page lists OrderPro products whose direct `products.supplier_id` is still missing. It reuses the
same OP-22A cleanup rows and priority scoring used by the CSV/XLSX export workflow.

The UI supports:

- Summary cards for missing suppliers, priority candidates, confirmed manual assignments, deferred
  reviews, rejected reviews, and completion percentage.
- Searching by SKU, barcode, product name, or description.
- Filters for priority only, open demand, stock on hand, cost, and existing suggestions.
- Candidate detail review with priority reasons, forecast readiness issues, suggestion evidence,
  stock, demand, and cost information.
- Server-side supplier search by supplier name or OrderPro supplier code.
- Explicit confirmation before assigning a supplier locally.
- Deferred, needs-information, and rejected review statuses without changing `products.supplier_id`.

Assignments through the UI:

- Resolve only an existing local supplier by exact `supplier_id`.
- Update `products.supplier_id` locally.
- Create or update `ProductSupplierAssignmentReview` with `status="confirmed"` and
  `suggestion_source="manual_supplier_cleanup"`.
- Store reviewer, notes, review timestamp, and evidence summary.
- Return `409 Conflict` if the product gained a different supplier after the page was loaded.

This UI does not create suppliers, edit supplier master data, call OrderPro, or write supplier changes
back to OrderPro.
