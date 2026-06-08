# OrderPro Demand Forecasting

OrderPro order history is the primary demand source for synced OrderPro products.
Forecasting must use the local `orderpro_orders` and `orderpro_order_items`
mirror tables only. Forecast requests must not call OrderPro.

## Status Classification

Observed OrderPro statuses are classified as:

- `shipped`: completed historical demand
- `confirmed`: open committed demand
- `packed`: open committed demand
- `backorder`: open committed demand
- `cancelled`: excluded

Historical demand defaults to shipped orders only:

```text
ORDERPRO_HISTORICAL_DEMAND_STATUSES=shipped
```

Open committed demand defaults to:

```text
ORDERPRO_OPEN_DEMAND_STATUSES=confirmed,packed,backorder
```

Excluded demand defaults to:

```text
ORDERPRO_EXCLUDED_DEMAND_STATUSES=cancelled
```

Aliases such as completed, fulfilled, closed, or paid should only be added to
the historical status setting if future discovery confirms they represent
fulfilled demand in this OrderPro account.

## Historical Demand

Historical shipped orders calculate:

- `avg_daily_usage`
- `observation_days`
- `shipped_units_in_window`
- `shipped_order_count`
- `demand_history_start`
- `demand_history_end`

`units_sold_in_window` and `eligible_order_count` are retained for backward
compatibility and mirror `shipped_units_in_window` and `shipped_order_count`.

Average daily usage uses the actual observed history range inside the lookback
window. It does not divide by the full configured lookback when only a shorter
range of history exists.

## Open Demand

Open committed demand calculates:

- `open_confirmed_units`
- `open_packed_units`
- `open_backorder_units`
- `total_open_demand`
- `effective_available_stock`

Effective available stock is:

```text
max(Product.current_stock - total_open_demand, 0)
```

Forecast decisions and days-until-stockout use effective available stock, not
raw current stock. Cancelled orders and negative quantities are excluded. Returns
should be modeled explicitly before they are used to reduce demand.

## Lookback

The default lookback is:

```text
FORECAST_DEMAND_LOOKBACK_DAYS=90
FORECAST_MIN_HISTORY_DAYS=14
```

`FORECAST_MIN_HISTORY_DAYS` is available for future confidence/risk tuning. It
does not currently force the average to divide by a minimum period.

## Fallback Behavior

Forecasting uses this order:

1. Eligible synced OrderPro shipped order items.
2. Existing Excel-derived `usage_history`.
3. No-history monitor behavior.

The Excel `sales_history_raw` and `usage_history` import flow remains available
during the transition.

## Forecast Demand Fields

Forecast responses include:

- `demand_source`: `orderpro_orders`, `usage_history`, `none`, or `not_applicable`
- `demand_lookback_days`
- `demand_history_start`
- `demand_history_end`
- `observation_days`
- `shipped_units_in_window`
- `shipped_order_count`
- `open_confirmed_units`
- `open_packed_units`
- `open_backorder_units`
- `total_open_demand`
- `effective_available_stock`
- `units_sold_in_window`
- `eligible_order_count`
- `excluded_order_count`
