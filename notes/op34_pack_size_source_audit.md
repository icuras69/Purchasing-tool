# OP-34 Pack-Size Source Audit and Read-Only Backfill Plan

## Goal

Create a read-only audit and backfill plan for pack size/order multiple data. OP-34 does not apply pack sizes, does not change forecast formulas, does not mutate recommendation rows, and does not call OrderPro.

## Pack-Size Sources Inspected

| Source | Field | Populated | Missing / not usable | Trusted now | Legacy evidence only | Risks | Recommended use |
| --- | --- | ---: | ---: | --- | --- | --- | --- |
| `product_forecast_input_profiles` | `pack_size` | 0 | 1,484 profile rows missing/non-positive; 3,713 products have no profile | Yes | No | Empty coverage today, but this is the current effective forecast input source. | Keep as canonical effective pack-size field. Future apply should only write here. |
| `product_suppliers` | `pack_size` | 1 | 492 rows missing/non-positive | No | Yes | Legacy mapping evidence can be stale, supplier-mismatched, duplicated, or rejected. | Use only as candidate evidence when unique, trusted, supplier-matched, and reasonable. |
| `product_master_items` | none | 0 | 1,153 rows with no pack-size field | No | Yes | No pack/order-multiple field exists in the model. | Do not use for pack size. |
| `products` | none | 0 | 5,197 products with no `Product.pack_size` column | No | No | Product model cannot directly store pack size today. | Do not treat product record as a pack-size source. |
| `purchase_order_lines` | `pack_size` | 0 | 95 rows missing/non-positive | No | Yes | Historical PO line snapshots may reflect one-off ordering context and not current supplier packaging. | Use only as diagnostic evidence, not automatic backfill input. |

## Safe Candidate Rules

A product is a safe pack-size candidate only when all of these are true:

1. Current effective `ProductForecastInputProfile.pack_size` is missing.
2. There is exactly one positive numeric legacy `ProductSupplier.pack_size` candidate.
3. Candidate mapping has a trusted status: `confirmed` or `matched`.
4. Product has a canonical `products.supplier_id`.
5. Candidate supplier matches the canonical product supplier.
6. Candidate pack size is positive and not greater than `1000`.
7. There are no conflicting positive legacy pack-size values.

Conflicts are reported and never resolved automatically.

## Endpoint Added

```text
GET /recommendations/pack-size-audit?sample_limit=25
```

The endpoint is read-only. It returns:

- total products
- products missing effective pack size
- products with existing profile pack size
- products with legacy `ProductSupplier.pack_size`
- safe candidate count
- conflict count
- no-candidate count
- products with recommendations blocked/review-only only because of missing pack size
- source counts
- top suppliers/products affected
- sample safe candidates
- sample conflicts
- recommendation impact simulation

## Local Audit Results

```text
Total products: 5,197
Products missing effective pack size: 5,197
Products with existing ProductForecastInputProfile.pack_size: 0
Products with legacy ProductSupplier.pack_size: 1
Products with one clear legacy pack-size candidate: 0
Safe candidate count: 0
Conflict count: 0
No-candidate count: 5,197
Products with recommendations blocked/review-only only because of missing pack size: 0
```

Top suppliers affected:

| Supplier | Missing pack-size products |
| --- | ---: |
| Missing supplier | 3,648 |
| Showtime | 404 |
| Agrihealth | 183 |
| Acravet Ltd | 115 |
| Triequestrian | 81 |
| Dairyspares | 73 |
| Mullinahone | 70 |
| Lister | 62 |
| Christies | 46 |
| Gallagher | 44 |

Sample safe candidates:

```text
None. No legacy pack-size row currently satisfies the full safe-candidate rule set.
```

Sample conflicts:

```text
None. The local database has no products with conflicting positive legacy pack-size values.
```

## Recommendation Impact Simulation

No recommendation impact simulation items were produced because there are zero safe pack-size candidates.

```text
Products simulated: 0
Would become order_ready: 0
Quantity would change: 0
Stale demand still needs review: 0
Missing cost still needs review: 0
```

Important policy result: no product would become `order_ready` in OP-34 because no pack-size backfill candidate is safe enough to simulate as applied.

## Files Changed

- `app/routes/recommendations.py`
- `app/services/pack_size_audit.py`
- `tests/test_pack_size_audit.py`
- `notes/op34_pack_size_source_audit.md`

## Tests Added

Backend tests cover:

- existing profile pack-size counts
- safe legacy candidates
- conflicting legacy pack-size candidates
- rejected/untrusted mappings excluded from safe candidates
- supplier mismatch excluded from safe candidates
- stale-only demand not becoming order-ready just because pack size is fixed
- endpoint read-only behavior
- helper and endpoint summary consistency

## Constraints Confirmed

- No OrderPro calls were added or run.
- No Render config was changed.
- No forecast formulas were changed.
- No database data was changed.
- No purchase orders were created.
- No pack sizes were automatically backfilled.
- Recommendations were not marked order-ready by this OP.

## Recommended OP-35

Focus OP-35 on pack-size evidence acquisition:

- Investigate why only one `ProductSupplier.pack_size` row is populated.
- Extend supplier/import mapping reports to capture supplier pack size/order multiple when present.
- Add a read-only import-quality report for source files that can provide pack size.
- Consider a controlled apply flow only after safe candidates exist and stakeholder-reviewed evidence rules are accepted.
