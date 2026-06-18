# Purchase Order CSV Export

The Purchase Orders detail view includes an **Export CSV** button when the selected purchase order has at least one line item.

Exporting calls:

```text
GET /purchase-orders/{purchase_order_id}/export.csv
```

The endpoint is protected by the normal authentication dependency. When `AUTH_ENABLED=false`, the centralized auth feature flag allows export without a bearer token for temporary staging use.

## File Format

The CSV uses UTF-8 with BOM so Microsoft Excel opens it cleanly. One row represents one purchase-order line item. Order-level totals and supplier metadata are repeated on every row to make filtering and imports easier.

Columns:

- `purchase_order_id`
- `status`
- `created_at`
- `updated_at`
- `approved_at`
- `issued_at`
- `expected_delivery_date`
- `currency`
- `order_notes`
- `supplier_id`
- `supplier_code`
- `supplier_name`
- `supplier_email`
- `supplier_phone`
- `supplier_lead_time_days`
- `product_id`
- `orderpro_product_id`
- `sku`
- `barcode`
- `product_name`
- `product_description`
- `category`
- `pack_size`
- `current_stock`
- `quantity`
- `unit_cost`
- `line_total`
- `order_subtotal`
- `order_total`
- `line_notes`
- `supplier_sku`
- `supplier_product_name`
- `minimum_order_quantity`
- `lead_time_days`

Optional values that are unavailable in the current local model are exported as blank cells.

## Safety

The export is read-only. It does not submit, approve, issue, receive, cancel, send to OrderPro, or otherwise modify a purchase order.

Text fields that begin with `=`, `+`, `-`, or `@` are prefixed with an apostrophe before writing the CSV to reduce spreadsheet formula-injection risk. Numeric fields are not altered.
