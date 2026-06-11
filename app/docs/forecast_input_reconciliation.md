# Forecast Input Reconciliation

OrderPro is the source of truth for the active product catalogue, supplier assignment,
inventory, and operational purchase/order data. This reconciliation layer fills in
forecast input gaps from deterministic local data that has already been synced or
created through the controlled purchase order workflow.

This process does not call OrderPro and does not write to OrderPro.

## What It Updates

Apply mode creates or updates `product_forecast_input_profiles` rows for current
OrderPro products. It does not mutate `products`, suppliers, purchase orders,
seasonality profiles, or historical sales data.

Forecasting and recommendation code can read the effective profile values to explain
where each input came from.

## Source Precedence

Cost:

1. `products.cost_price` from OrderPro product sync
2. latest mirrored OrderPro purchase order line `unit_cost`
3. latest local purchase order line `unit_cost`
4. missing

Lead time:

1. `products.lead_time_days`
2. `suppliers.lead_time_days`
3. legacy `product_suppliers.lead_time_days` as low-confidence transition evidence
4. missing

Minimum order quantity:

1. `products.min_order_qty`
2. business default `1`

Pack size:

1. `products.pack_size` if present in the runtime model/data
2. missing

Safety stock:

1. `products.safety_stock`
2. business default `0`

## Readiness Semantics

Blocking issue:

- `missing_supplier`: product has no current OrderPro supplier assignment.

Warnings:

- `missing_cost`: no deterministic product or PO cost found.
- `missing_lead_time`: neither product nor supplier has usable lead time.
- `missing_pack_size`: pack size is unavailable.
- `fallback_moq`: minimum order quantity fell back to the business default.
- `missing_demand_history`: no usable shipped/open demand or reconciled historical demand.

Seasonality remains advisory. This reconciliation does not activate seasonal
multipliers and does not change seasonality profiles.

## Commands

Dry-run all OrderPro products:

```powershell
python scripts/reconcile_forecast_inputs.py --dry-run --save-report
```

Dry-run a single supplier:

```powershell
python scripts/reconcile_forecast_inputs.py --dry-run --supplier-id 34 --save-report
```

Apply profile refresh:

```powershell
python scripts/reconcile_forecast_inputs.py --apply --save-report
```

Reports are saved under `tmp/forecast_input_reconciliation_reports/`, which is
ignored by Git.

## Verification SQL

```sql
select
  cost_source,
  lead_time_source,
  moq_source,
  pack_size_source,
  count(*)
from product_forecast_input_profiles
group by cost_source, lead_time_source, moq_source, pack_size_source
order by count(*) desc;
```

```sql
select
  count(*) filter (where cost_price is not null) as profiles_with_cost,
  count(*) filter (where lead_time_days is not null) as profiles_with_lead_time,
  count(*) filter (where blocking_issues::text like '%missing_supplier%') as profiles_missing_supplier
from product_forecast_input_profiles;
```
