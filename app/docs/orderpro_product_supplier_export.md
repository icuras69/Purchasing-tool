# OrderPro Product Supplier Export

The OrderPro product API does not currently expose supplier assignment for every product. A fresh OrderPro product export can provide supplier fields that are not available through the API, so this workflow imports that file into the local supplier assignment review process.

This is local-only. It does not write to OrderPro.

## Expected Columns

Column names are matched case-insensitively. Spaces and dashes are treated like underscores.

Product identity:

- `id`
- `product_id`
- `orderpro_id`
- `orderpro_product_id`
- `sku`
- `product_sku`
- `orderpro_sku`
- `barcode`
- `ean`
- `upc`
- `name`
- `product_name`

Supplier identity:

- `supplier_code`
- `supplier`
- `supplier_ref`
- `supplier_id`
- `orderpro_supplier_id`
- `supplier_name`
- `supplier_sku`
- `supplier_product_code`

Each row needs at least one product identifier and at least one supplier identifier.

## Product Matching

Product matching precedence:

1. Exact OrderPro product id to current OrderPro products only.
2. Exact export SKU to current OrderPro SKU-like fields only: `products.sku` if the model has one, then `products.orderpro_sku`.
3. Exact barcode to current OrderPro products only, only when the barcode is unique among current OrderPro products.
4. No match.

Current OrderPro products are rows where `source_system = "orderpro"`, `orderpro_id` is present, or `orderpro_sku` is present. Blank SKU, barcode, and product id values are ignored. `products.source_key` is not used as a current OrderPro SKU because legacy/import rows can use it for non-authoritative identifiers; it is only used for legacy diagnostics.

Legacy/local product rows are diagnostic only for this import. If a SKU or barcode matches multiple products globally but exactly one current OrderPro product, the current OrderPro product is used and the duplicate legacy match is reported. If a SKU or barcode matches multiple current OrderPro products, the row is not auto-matched.

The report distinguishes unique duplicate keys from affected rows:

- `duplicate_orderpro_sku_key_count`: count of unique duplicate SKU keys among current OrderPro products.
- `rows_with_duplicate_orderpro_sku_match`: export rows that attempted to use a duplicate current OrderPro SKU key.
- `duplicate_orderpro_barcode_key_count`: count of unique duplicate barcode keys among current OrderPro products.
- `rows_with_duplicate_orderpro_barcode_match`: export rows that attempted to use a duplicate current OrderPro barcode key.

## Supplier Matching

Supplier matching precedence:

1. Exact supplier code to `suppliers.orderpro_code`.
2. Exact OrderPro supplier id to `suppliers.orderpro_id`.
3. Exact normalized supplier name, only when unique.
4. No match.

Name-only supplier matches are suggestions only. They are never auto-confirmed.

## Confirmation Rules

`--confirm-exact-code` only confirms locally when:

- the product matched by exact OrderPro id, exact current OrderPro SKU, or unique current OrderPro barcode;
- the supplier matched by exact supplier code or exact OrderPro supplier id;
- the product has no existing conflicting `supplier_id`.

Existing matching supplier assignments are treated as idempotent. Existing conflicting supplier assignments are reported and not overwritten.

## Commands

Dry-run:

```powershell
..venv\Scripts\python.exe scripts\import_orderpro_product_supplier_export.py --file "PATH_TO_EXPORT.csv" --dry-run --save-report
```

Apply suggestions only:

```powershell
..venv\Scripts\python.exe scripts\import_orderpro_product_supplier_export.py --file "PATH_TO_EXPORT.csv" --apply-suggestions --save-report
```

Confirm exact code/id matches locally:

```powershell
..venv\Scripts\python.exe scripts\import_orderpro_product_supplier_export.py --file "PATH_TO_EXPORT.csv" --confirm-exact-code --save-report
```

Do not run confirmation until the dry-run report has been reviewed.

## Why Fuzzy Matching Is Forbidden

Supplier assignment changes directly affect supplier forecasts and draft purchase order generation. Product names, descriptions, brands, and categories are not reliable supplier identity fields. This workflow therefore refuses fuzzy matching and never infers supplier from product name alone.

## Forecast Impact

Unconfirmed export suggestions do not affect forecasts or purchase order generation. Once an exact supplier assignment is confirmed locally, `products.supplier_id` becomes available to the existing forecast and supplier forecast logic.
