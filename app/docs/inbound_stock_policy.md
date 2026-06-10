# Inbound Stock Policy

Inbound stock is supplier stock already on open purchase orders. Forecasting uses
it as a non-advisory quantity input so the system does not recommend buying
units that are already on order.

## Included Sources

Current implementation includes local purchase order workflow lines when the PO
header status is:

- `approved`
- `issued`

These statuses mean a human has approved the supplier purchase or marked it as
internally issued.

The implementation also includes read-only mirrored OrderPro purchase orders
when the mirrored status is one of:

- `sent`
- `partial`
- `partially_received`

The OrderPro mirror is populated from GET-only API calls and does not create,
approve, issue, receive, cancel, or edit OrderPro purchase orders.

## Excluded Sources

The following local PO statuses are excluded:

- `draft`
- `pending_approval`
- `cancelled`
- `received`

Draft and pending approval POs are not committed supplier stock. Cancelled and
received POs should not create new inbound supply.

The following OrderPro mirror statuses are excluded:

- `cancelled`
- `canceled`
- `closed`
- `received`
- `fully_received`
- `draft`
- `rejected`
- `void`

## Quantity Formula

For each product:

```text
incoming_qty = sum(max(ordered_qty - received_qty - cancelled_qty, 0))
```

The current local PO line table has `quantity`, but does not yet have line-level
`received_qty` or `cancelled_qty`. Until those fields exist, the fallback is:

```text
incoming_qty = sum(max(line.quantity, 0))
```

The inbound stock response includes a warning when this fallback is used.

For OrderPro mirrored purchase order lines, the sync stores:

- `quantity_ordered`
- `quantity_received`
- `quantity_cancelled`
- `quantity_open`

If OrderPro provides a reliable open/remaining quantity field, it is stored as
`quantity_open`. Current OrderPro purchase order line samples expose:

- `qty`: remaining/open quantity
- `qty_received`: received quantity
- `unit_cost`: line unit cost
- `total`: line total

For those payloads, the mirror stores:

```text
quantity_open = qty
quantity_received = qty_received
quantity_cancelled = 0
quantity_ordered = qty + qty_received
```

This is why a fully received OrderPro line can have `qty = 0` and
`qty_received > 0`: it contributes no inbound stock.

If no open quantity field is present, the sync falls back to:

```text
quantity_open = max(quantity_ordered - quantity_received - quantity_cancelled, 0)
```

If received quantity is missing for the fallback calculation, the sync uses `0`
and records a warning count. OrderPro does not expose cancelled quantity in the
sampled line shape, so the report records one note and uses `0`; it does not
emit the same missing-cancelled warning for every line.

## Linking Rules

OrderPro PO lines are linked to current products with deterministic matches
only:

1. OrderPro product ID.
2. Exact SKU / `products.orderpro_sku`.
3. Exact barcode only when that barcode is unique locally.

Supplier headers are linked with:

1. OrderPro supplier ID.
2. Supplier code.
3. Exact normalized supplier name only when unique.

Ambiguous matches remain unlinked and are reported by the sync planner. No fuzzy
matching is used.

## Forecast Impact

Forecasting now calculates:

```text
recommended_qty_before_inbound = shortage before supplier POs
recommended_qty_after_inbound = shortage after approved/issued incoming POs
effective_available_stock_for_reorder =
    current_stock + incoming_qty - open_customer_demand
```

The final `recommended_qty` uses the after-inbound value. It is never allowed to
go below zero.

## Examples

If current stock is `0`, open customer demand is `64`, and approved incoming
supplier PO quantity is `20`:

```text
recommended_qty_before_inbound = 64
recommended_qty_after_inbound = 44
```

If incoming supplier PO quantity is `100`, the shortfall is fully covered:

```text
recommended_qty_after_inbound = 0
recommended_action = monitor
```

## Limitations

- Expected delivery dates are available only if local PO `delivery_date` is set.
- Partial receiving is not represented at the PO line level yet.
- OrderPro purchase order expected dates depend on the fields exposed by the
  read-only API payload.
- Missing received quantities use documented fallback warnings when fallback
  calculation is needed.
- Missing cancelled quantity is handled as a report-level note for the sampled
  OrderPro line shape.
- No purchase orders are approved, issued, received, or sent externally by this
  calculation.

Seasonality remains advisory and does not alter inbound stock calculations.
