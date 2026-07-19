# Forecast Pack Rules PRD Implementation Note

## Implemented foundation

This pass adds the backend foundation for management-friendly pack-rounded recommendations without changing OrderPro data or external purchase behavior.

Implemented:

- `product_pack_rules` table and SQLAlchemy model.
- Active product/SKU pack-rule resolver.
- Pure pack-rounding helper with:
  - raw required quantity
  - MOQ-adjusted pre-pack quantity
  - final rounded quantity
  - order multiple
  - pack display
  - rounding explanation
  - missing-rule warnings
- Forecast response fields for `raw -> final` pack traceability.
- Recommendation explanations and snapshots now carry pack-rule context.
- Recommendation manager CSV exports include raw quantity, final quantity, order multiple, pack rule, rule source, and rounding explanation.
- Local PO draft line snapshots preserve configured pack-rule order multiple in the existing line `pack_size` field and append the pack explanation to line notes.
- Forecast UI displays the pack-rule context in the existing forecast detail view.

## Rounding policy

For reorder forecasts:

```text
raw_required_quantity = demand/stock/inbound shortage from the existing forecast engine
pre_pack_quantity = max(raw_required_quantity, MOQ) when raw_required_quantity > 0
final_recommended_quantity = ceil(pre_pack_quantity / order_multiple) * order_multiple
```

Zero or negative raw required quantity remains `0` and does not become a reorder recommendation.

## Pack-rule precedence

Current resolver precedence:

1. Active rule for `product_pack_rules.product_id`.
2. Active rule for exact `product_pack_rules.canonical_sku`.
3. Existing reconciled/legacy pack size as compatibility fallback.
4. Default order multiple `1` with an explicit warning in `pack_rule_warnings`.

The compatibility fallback preserves existing pack-size behavior until the agreed pack-rule sheet is imported and verified.

## Not implemented yet

The PRD is broader than this foundation pass. Still pending:

- Product group/range rule matching.
- Import/seed workflow for the agreed Uniblock/Jakoti/Himalayan rules once verified product IDs/SKUs are supplied.
- Manager quantity override model with required override reason.
- Full Recommendations page redesign with active-filter summary cards and action-priority sorting.
- Suggested PO preview editing that validates non-multiple overrides.
- Dedicated pack-rule admin/review UI.

## Safety

- No OrderPro calls are added.
- No OrderPro product data is changed.
- No purchase orders are automatically created, approved, issued, or sent.
- Stale-demand and canonical supplier safeguards remain in place.
