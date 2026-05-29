# OrderPro Source Of Truth Plan

## Business Rules

OrderPro is the source of truth for products, suppliers, current stock, warehouses, and purchase orders.

One product has exactly one active supplier. Similar products from different suppliers should be represented as separate products, not as one product with multiple supplier mappings.

The current `product_suppliers` table remains legacy during the transition. It should not be treated as the future authoritative purchasing model.

## Current Transition Position

Existing local products, suppliers, supplier mappings, and local purchase order data should be treated as temporary or test data until OrderPro sync is verified. Do not wipe the local data yet. The safe path is to add OrderPro identity fields, run dry-run sync reports, verify row matching, and only then replace or deactivate local-only records.

## CSV Product Export Findings

The uploaded product export `products_export_2026-05-29.csv` contains:

- `1481` product rows.
- `sku` on every row.
- `1481` unique `sku` values.
- `name` on every row.
- `barcode` on `1113` rows, with `1108` unique barcode values.
- `supplier_code` on `866` rows, with `35` unique supplier codes.
- `supplier_sku` on only `35` rows.
- `cost_price` on `171` rows.
- `sell_price` on every row.

CSV columns:

- `sku`
- `name`
- `barcode`
- `category`
- `uom`
- `weight_kg`
- `cost_price`
- `sell_price`
- `hs_code`
- `country_of_origin`
- `image_url`
- `supplier_code`
- `supplier_sku`

The CSV does not include warehouse, location, current stock, active/inactive, or purchase order fields. Those must be discovered through the OrderPro API.

## Target Product/Supplier Direction

Future product records should use:

- `products.orderpro_sku` as the main product identifier.
- `products.supplier_id` as the active supplier relationship.
- `products.supplier_sku` for the supplier-specific SKU when OrderPro provides it.

Future supplier records should use:

- `suppliers.orderpro_id` when available from the API.
- `suppliers.orderpro_code` when only supplier code is available.

## Legacy ProductSupplier Role

`product_suppliers` should be converted to non-authoritative legacy/audit data after the new OrderPro product model is in place. Existing rows may be useful for historical local decisions, but new forecasting, recommendations, and draft purchase order generation should eventually use `products.supplier_id` instead.

## No Write-Back Yet

This phase is read-only. The token should require only read permissions. No OrderPro write endpoints should be called until explicit write-back design, approval, and tests are added.
