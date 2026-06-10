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

## Excluded Sources

The following local PO statuses are excluded:

- `draft`
- `pending_approval`
- `cancelled`
- `received`

Draft and pending approval POs are not committed supplier stock. Cancelled and
received POs should not create new inbound supply.

OrderPro purchase order mirror data is not currently available in a dedicated
local mirror table, so it is not counted yet.

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
- OrderPro purchase order mirror data is not counted until a dedicated read-only
  mirror is added.
- No purchase orders are approved, issued, received, or sent externally by this
  calculation.

Seasonality remains advisory and does not alter inbound stock calculations.
