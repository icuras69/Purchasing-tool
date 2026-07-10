# OP-33 Pack Size, MOQ, and Existing Recommendation Cleanup Guardrails

## Goal

Improve purchase-quality guardrails without changing data, calling OrderPro, or mutating existing recommendation rows. OP-33 adds a purchase-readiness classification to recommendation explanations/audits, adds a read-only cleanup-candidates endpoint for existing recommendation rows, and surfaces MOQ/pack-size review signals in recommendation details.

## Current MOQ and pack-size behavior found

MOQ is resolved in `app/services/forecast_input_reconciliation.py` through `profile_or_effective_inputs()`. The product record `min_order_qty` wins when positive. If the product MOQ is missing or non-positive, the service falls back to `1.0` with `moq_source="business_default"`. A `ProductForecastInputProfile.min_order_qty` can override the fallback/business-default MOQ.

Pack size is also resolved in `profile_or_effective_inputs()`, but `Product` has no direct `pack_size` column in the current model. Effective pack size therefore comes from `ProductForecastInputProfile.pack_size` when present; otherwise `pack_size` is `null` and `pack_size_source="missing"`. Existing legacy `ProductSupplier.pack_size` exists as mapping evidence, but the current OrderPro-source-of-truth forecast path does not use that legacy mapping as the active pack-size source.

Forecast quantity rounding is handled in `app/services/forecasting.py`:

- Raw reorder need is calculated from projected lead-time demand, open demand, safety stock, current stock, and incoming stock.
- If raw need is positive, the forecast raises the recommendation to at least the effective MOQ.
- `round_order_quantity()` ceilings the quantity to an integer and rounds up to a pack-size multiple when an effective pack size exists.
- If pack size is missing, the forecast still produces an integer quantity and now marks purchase readiness as review-needed rather than order-ready.

Recommendation creation in `app/services/recommendations.py` uses the forecast quantity and still does not create purchase orders automatically. Recommendation-to-PO conversion remains guarded by the existing accepted-recommendation and `ProductSupplier` mapping requirements. OP-33 does not change PO conversion behavior; it exposes whether a row is safe to order as-is before a manager acts.

## Purchase-readiness statuses

Added to `/recommendations/explain` and `/recommendations/audit`:

```text
order_ready
needs_review
blocked
```

`order_ready` requires an actionable reorder, supplier, lead time, non-stale demand, positive quantity, MOQ satisfaction, and pack-size satisfaction with a known pack-size input.

`needs_review` is returned when the recommendation is plausible but not safe to order as-is, including missing pack size, missing cost, stale-only advisory demand, fallback MOQ, unusual returns/negative demand, MOQ raising, or pack-size rounding.

`blocked` is returned for hard blockers such as missing supplier, missing lead time, no demand/open demand, non-positive quantity, non-inventory products, or a forecast action that is not reorder.

New explanation fields include:

- `purchase_readiness_status`
- `purchase_readiness_issues`
- `purchase_readiness`
- `suggested_cleanup_action`
- `not_ready_for_po`
- `pack_size`
- `pack_size_source`
- `quantity_satisfies_moq`
- `quantity_satisfies_pack_size`
- `quantity_was_raised_to_moq`
- `quantity_was_rounded_to_pack_size`
- `quantity_review_note`

## Cleanup candidates endpoint

Added read-only endpoint:

```text
GET /recommendations/cleanup-candidates?limit=500
```

It returns existing recommendation rows that need review, grouped by issue and suggested advisory action. It does not update, reject, delete, or convert recommendations.

Issue groups include:

- `stale-only actionable existing row`
- `missing supplier`
- `missing lead time`
- `no demand`
- `non-positive quantity`
- `quantity below MOQ`
- `missing pack size`
- `cost missing`
- `enough stock/no reorder needed`

Suggested actions are advisory only:

- `review`
- `convert_to_watchlist`
- `reject_existing_recommendation`
- `update_after_supplier_fix`
- `update_after_pack_size_fix`

## Current local impact

Read-only verification found:

```text
Total products: 5,197
Products missing effective pack size: 5,197
OrderPro products missing effective pack size: 1,484
Existing recommendation rows: 9
Existing recommendations missing pack size: 9
Existing recommendations needing cleanup: 9
```

Cleanup issue counts:

```text
missing pack size: 9
stale-only actionable existing row: 7
quantity raised to MOQ: 5
cost missing: 1
enough stock/no reorder needed: 2
non-positive quantity: 2
```

Cleanup action counts:

```text
update_after_pack_size_fix: 9
```

## Verification products

| Product ID | Explanation status | Purchase readiness | MOQ | Pack size | Recommended qty | Blockers | Suggested action |
| --- | --- | --- | ---: | --- | ---: | --- | --- |
| 3020 | needs_review | needs_review | 1.0 product_record | missing | 6.0 | none | update_after_pack_size_fix |
| 3004 | needs_review | needs_review | 1.0 product_record | missing | 2.0 | none | update_after_pack_size_fix |
| 3021 | needs_review | needs_review | 1.0 product_record | missing | 1.0 | none | update_after_pack_size_fix |
| 3121 | needs_review | needs_review | 1.0 product_record | missing | 7.0 | none | update_after_pack_size_fix |
| 3180 | needs_review | needs_review | 1.0 product_record | missing | 1.0 | none | update_after_pack_size_fix |
| 3207 | needs_review | needs_review | 1.0 product_record | missing | 1.0 | none | update_after_pack_size_fix |
| 7721 | monitor | blocked | 1.0 product_record | missing | 0.0 | none | convert_to_watchlist |
| 3001 | blocked | blocked | 1.0 product_record | missing | 0.0 | Missing supplier; Missing lead time | update_after_supplier_fix |

Common warning across these products: `Missing pack size; quantity should be reviewed before PO creation`. Products 3020, 3004, 3021, 3121, 3180, and 3207 also remain stale-only legacy-demand review items from OP-32.

## Files changed

- `app/routes/recommendations.py`
- `app/services/recommendation_audit.py`
- `app/services/recommendations.py`
- `frontend/src/App.tsx`
- `frontend/src/App.test.tsx`
- `tests/test_recommendations.py`
- `notes/op33_pack_moq_recommendation_guardrails.md`

## Tests added or updated

Backend tests now cover:

- Order-ready recommendation with valid supplier, lead time, demand, MOQ, and pack size.
- Missing pack size produces `needs_review`, not silent order-ready.
- Quantity below MOQ is raised and flagged.
- Quantity rounded to pack size is flagged.
- Stale-only recommendation remains not order-ready.
- Existing stale-only actionable recommendation appears in cleanup candidates.
- Missing supplier and lead time remain blocked.
- Cleanup-candidates endpoint is read-only.
- Existing explain/audit endpoints still return expected data.

Frontend tests now cover purchase-readiness fields in the recommendation details panel.

## Constraints confirmed

- No OrderPro calls were added or run.
- No Render config was changed.
- No database data was changed.
- Existing recommendation rows are not deleted, rejected, converted, or mutated automatically.
- Purchase orders are not created automatically.

## Recommended OP-34

Focus OP-34 on pack-size source remediation:

- Decide the canonical source for pack size/order multiple now that `Product` has no direct pack-size column.
- Determine whether confirmed `ProductSupplier.pack_size` can safely populate `ProductForecastInputProfile.pack_size`.
- Add a read-only pack-size backfill plan/report before any apply step.
- Consider a manager-facing cleanup/watchlist page for `cleanup-candidates` once the pack-size source policy is settled.
