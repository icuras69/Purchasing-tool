# Product Search And Performance Baseline

## Unified Product Search

Product-based list screens use the same search precedence:

1. Exact `products.id`.
2. Exact OrderPro SKU.
3. Exact barcode.
4. Exact supplier SKU.
5. Partial product name or description.
6. Supplier name or code when that context is available.

Numeric searches prioritize an exact local product ID inside the current result scope. If no scoped product ID matches, the search can still match SKU-like fields.

## Instrumentation

Slow report and list endpoints emit lightweight log lines through `app.performance`:

```text
PERF <endpoint> elapsed_ms=<milliseconds> key=value ...
```

The logs intentionally avoid payload data and secrets. They record endpoint name, filter parameters, returned row counts, totals when already computed, and whether summary-style calculations were performed. They are a baseline for later query tuning and caching work; no caching is added yet.

Current instrumented areas include:

- Product list and unmapped product list.
- Legacy product-supplier mapping list.
- Forecast readiness summary/list.
- Forecast input reconciliation summary/list.
- Demand history summary/list.
- Manual supplier cleanup summary/candidates.
- Seasonality summary/products.
- Recommendations list.
