# OrderPro API Discovery

## Purpose

Before changing the database schema, use read-only API discovery to inspect real OrderPro payloads for products, suppliers, inventory, warehouses, purchase orders, and orders. This prevents building migrations around guessed field names.

## Required Environment Variables

Use `.env` locally. Do not commit `.env`.

```text
ORDERPRO_API_BASE_URL=https://wms.orderpro.cloud/api/v2
ORDERPRO_API_TOKEN=your-read-only-token
ORDERPRO_SYNC_ENABLED=true
ORDERPRO_TIMEOUT_SECONDS=30
```

`ORDERPRO_SYNC_ENABLED` defaults to `false`. Discovery scripts refuse to call OrderPro unless it is explicitly true and the script is run with `--run`.

## Required Token Permissions

This phase needs read-only permissions:

- `products:read`
- `inventory:read`
- `suppliers:read`
- `purchase-orders:read`
- `warehouses:read`
- `orders:read` optional

Do not grant write permissions for this phase.

## Discovery Command

From the project root:

```powershell
$env:ORDERPRO_API_BASE_URL='https://wms.orderpro.cloud/api/v2'
$env:ORDERPRO_API_TOKEN='...'
$env:ORDERPRO_SYNC_ENABLED='true'
.\.venv\Scripts\python.exe scripts\discover_orderpro_api.py --run --save-samples
```

Optional page-2 check:

```powershell
.\.venv\Scripts\python.exe scripts\discover_orderpro_api.py --run --fetch-page-2
```

Optional warehouse/location alternatives:

```powershell
.\.venv\Scripts\python.exe scripts\discover_orderpro_api.py --run --include-warehouse-alternatives
```

Optional stock-count/custom endpoint discovery:

```powershell
.\.venv\Scripts\python.exe scripts\discover_orderpro_api.py --run --include-stock-count --save-samples
```

Custom endpoints can be tested with:

```powershell
.\.venv\Scripts\python.exe scripts\discover_orderpro_api.py --run --extra-endpoint /stock-count
.\.venv\Scripts\python.exe scripts\discover_orderpro_api.py --run --extra-url https://wms.orderpro.cloud/stock-count
```

Full URLs are allowed only for the configured OrderPro host. Unknown external hosts are refused by default.

The script tests these read-only endpoints by default:

- `/products`
- `/inventory`
- `/suppliers`
- `/purchase-orders`
- `/warehouses`
- `/orders`

When `--include-warehouse-alternatives` is used, the script also tests:

- `/warehouse`
- `/locations`
- `/inventory/warehouses`
- `/warehouse-locations`
- `/lots`

When `--include-stock-count` is used, the script also tests:

- `https://wms.orderpro.cloud/stock-count`
- `/stock-count`
- `/api/v2/stock-count`
- `/stock-counts`

Failures are reported per endpoint without stopping the whole discovery run.

## Output

For each endpoint, the script prints:

- endpoint tested
- status code
- content type
- whether the response is JSON
- top-level JSON shape
- top-level keys
- detected response style
- first-record keys
- nested object keys when the endpoint wraps records in a nested paginator
- count of records in the first payload
- pagination clues including current page, last page, per page, total, next page URL, and next page number
- warnings for unexpected nested response shapes
- a sanitized text/HTML preview of at most 300 characters for non-JSON responses

When `--save-samples` is used, sanitized summary and first-record samples are written to:

```text
tmp/orderpro_samples/
```

The script does not save full raw payloads by default. To save sanitized full raw payloads, pass `--save-raw` explicitly.

The `tmp/` folder is gitignored. The script removes keys containing `token` from saved samples and never prints the configured token.

## Observed Response Shapes

Current discovery has observed:

- `/products`: works; returns a top-level object with `data`, `links`, and `meta`.
- `/inventory`: works; returns a top-level object with `data`, `links`, and `meta`.
- `/orders`: works; returns a top-level object with `data`, `links`, and `meta`.
- `/suppliers`: works, but `data` appears to contain a nested paginator object with its own `data` records.
- `/purchase-orders`: works, but `data` appears to contain a nested paginator object with its own `data` records.
- `/warehouses`: returns a 500 server error.
- `https://wms.orderpro.cloud/stock-count`: requires discovery and may be an HTML page rather than a JSON API endpoint.

Inventory records contain warehouse information such as `warehouse` and `warehouse_id`, so warehouses may be derivable from inventory if `/warehouses` remains unavailable.

Known CSV product export fields:

- `sku` is unique and should be treated as the primary product key.
- `name` is present on all rows.
- `barcode`, `category`, `uom`, `weight_kg`, `cost_price`, `sell_price`, `hs_code`, `country_of_origin`, and `image_url` are product attributes.
- `supplier_code` exists on some products and should map to future supplier identity.
- `supplier_sku` is sparse and must remain optional.
- The CSV export does not include stock, warehouse, active/inactive, or purchase order fields.

## Next Required Discovery Step

Before writing migrations, capture sanitized summaries for `/products`, `/inventory`, `/suppliers`, `/purchase-orders`, and `/orders`, plus warehouse/location alternatives and stock-count endpoints. Confirm exact product ID/SKU fields, supplier code/ID fields, inventory warehouse fields, PO header fields, PO line fields, stock-count response type, and pagination behavior.

## Safety Rules

- GET only.
- No POST, PATCH, PUT, or DELETE.
- No token logging.
- No database writes.
- No schema changes.
- No frontend changes.
- No write-back to OrderPro.
