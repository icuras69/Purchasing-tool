# Clean Purchase Order CSV Export

The Purchase Orders detail view includes an **Export Clean CSV** button when the selected purchase order has at least one line item.

Exporting calls:

```text
GET /purchase-orders/{purchase_order_id}/export.csv
```

The endpoint is protected by the normal authentication dependency. When `AUTH_ENABLED=false`, the centralized auth feature flag allows export without a bearer token for temporary staging use.

## User-Friendly File Format

The CSV uses UTF-8 with BOM so Microsoft Excel opens it cleanly. One row represents one purchase-order line item.

The export deliberately contains only the fields needed to review or share an order:

- `PO Number`
- `Supplier`
- `Status`
- `Expected Delivery`
- `SKU`
- `Product`
- `Supplier SKU`
- `Quantity`
- `Pack Size`
- `Packs`
- `MOQ`
- `Unit Cost`
- `Line Total`
- `Currency`
- `Notes`

Internal database IDs, audit timestamps, supplier contact details, product descriptions, stock levels, duplicated totals, and other technical fields are excluded. Those details remain available inside the tool and in the local handoff packet where needed.

Optional values that are unavailable are exported as blank cells. The file name follows:

```text
PO-{number}_{supplier}_{created-date}.csv
```

`Packs` is calculated as quantity divided by pack size. It stays blank when a valid pack size is unavailable.

## When To Use Each Download

- **Export Clean CSV**: use for day-to-day review, Excel cleanup, or sharing an uncluttered line-item list.
- **Download handoff packet**: use after a PO is locally issued when technical local and OrderPro linkage details are needed. The handoff packet still does not send anything externally.

## Safety

The export is read-only. It does not submit, approve, issue, receive, cancel, send to OrderPro, or otherwise modify a purchase order.

Text fields that begin with `=`, `+`, `-`, or `@` are prefixed with an apostrophe before writing the CSV to reduce spreadsheet formula-injection risk. Numeric fields are not altered.
