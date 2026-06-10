# Seasonality Methodology

Seasonality is advisory in this project stage. It does not change `recommended_qty`, `reorder_point`, purchase order quantities, approval, issuing, or OrderPro synchronization.

## Source Tables Audited

### Primary calculation source

`usage_history`

- Date column: `date`
- Quantity columns: `qty_used`, `qty_returned`, `net_qty`
- Product identifier: `product_id`
- Source marker: `source_system`, normally `historical_sales_excel`
- Meaning: normalized product-level daily usage/sales derived from imported historical sheets.

`usage_history` is used because it is already matched to local products and separates sold/used quantity from returned quantity.

### Raw audit source

`sales_history_raw`

- Date column: `txn_date`
- Quantity column: `quantity`
- Product matching column: `product_id`
- SKU/product clues: `barcode_clean`, `description`, `source_key`, `code`
- Return marker: `is_return`
- Non-inventory marker: `is_non_inventory`
- Meaning: raw imported Excel source rows from historical sales sheets.

Raw rows remain audit evidence and are used for unmatched-row counts. They are not directly used for the initial seasonality calculation to avoid duplicating matching logic already represented in `usage_history`.

## Current Local Historical Audit

Read-only audit run on 2026-06-10:

- Source table used: `usage_history`
- Date column: `date`
- Quantity columns: `qty_used`, `qty_returned`, `net_qty`
- Product identifier columns: `product_id`
- Earliest history date: 2022-01-01
- Latest history date: 2025-12-03
- Historical rows evaluated: 24,262
- Matched usage rows: 24,262
- Products with historical matches: 3,616
- Unmatched inventory rows in `sales_history_raw`: 0
- Negative/return rows: 627
- Months represented: 48
- The imported data represents historical sales/fulfilled usage from Excel-derived sheets, not current open OrderPro demand.

## Historical Data Audit Queries

```sql
select
  min(date) as history_start,
  max(date) as history_end,
  count(*) as usage_rows,
  count(distinct product_id) as matched_products,
  sum(case when net_qty < 0 or qty_returned > 0 then 1 else 0 end) as negative_or_return_rows
from usage_history;
```

```sql
select count(*) as unmatched_inventory_raw_rows
from sales_history_raw
where row_type = 'inventory'
  and product_id is null;
```

```sql
select date_trunc('month', date)::date as month, count(*) as rows
from usage_history
group by 1
order by 1;
```

## Seasonal Calendar

Default calendar is the Northern Hemisphere market calendar:

- winter: December, January, February
- spring: March, April, May
- summer: June, July, August
- autumn: September, October, November

This represents the business market calendar, not the developer or user's physical location.

## Monthly Demand Calculation

For each product:

1. Read matched `usage_history` rows.
2. Group by year and calendar month.
3. Use `net_qty` as the monthly quantity basis.
4. Negative monthly totals are clamped to zero for classification while negative/return rows are counted and reported.
5. Missing months are not automatically treated as zero demand. They are excluded unless there is evidence of activity in that month.
6. Average each calendar month across observed years.

Monthly index:

```text
monthly_index =
average units in that calendar month across available years
/
average monthly units across observed calendar months
```

The profile stores both `monthly_units` and `monthly_indices` so later backtesting can tune thresholds without re-importing source data.

## Initial Classification Rules

Calculation version: `seasonality-v1`

Allowed `seasonality_tag` values:

- `winter`
- `spring`
- `summer`
- `autumn`
- `multi_peak`
- `year_round`
- `insufficient_data`

Rules:

- `insufficient_data` when history coverage is shorter than the configured minimum, active months are too sparse, fewer than two years are covered, or total units are zero.
- `year_round` when coefficient of variation is low and no meaningful monthly peak exists.
- A single season when one season clearly exceeds baseline and nearby seasons do not produce a similar peak.
- `multi_peak` when multiple seasons have elevated demand without one clear primary season.

One extreme order is prevented from creating a high-confidence season by penalizing profiles where one calendar month represents more than 45% of all observed units.

## Confidence Method

Confidence score combines:

- years covered
- active months
- total volume
- seasonality strength
- one-off order penalty

Labels:

- `high`: score >= 0.75
- `medium`: score >= 0.50
- `low`: score < 0.50
- `insufficient`: used for `insufficient_data`

## Current-Season Status

Dynamic status is calculated at request time and is not stored on `products`.

Statuses:

- `in_season`
- `approaching_season`
- `off_season`
- `year_round`
- `insufficient_data`

`approaching_season` means a peak month starts within the configured 1-2 month lookahead window and handles year boundaries, for example November approaching a December winter peak.

## Product Tag Population

After profiles are applied, `products.seasonality_tag` is updated from the calculated profile tag.

The tag describes recurring profile type only. It does not describe whether the product is currently in season.

## SQL Examples

Classification counts:

```sql
select seasonality_tag, count(*)
from product_seasonality_profiles
group by seasonality_tag
order by count(*) desc;
```

Products currently in season for June:

```sql
select p.id, p.orderpro_sku, p.name, sp.seasonality_tag, sp.monthly_indices ->> '6' as june_index
from products p
join product_seasonality_profiles sp on sp.product_id = p.id
where sp.seasonality_tag <> 'insufficient_data'
  and (
    sp.peak_months::jsonb @> '[6]'::jsonb
    or nullif(sp.monthly_indices ->> '6', '')::numeric >= 1.2
  )
order by nullif(sp.monthly_indices ->> '6', '')::numeric desc;
```

Products approaching season from November:

```sql
select p.id, p.orderpro_sku, p.name, sp.seasonality_tag, sp.peak_months
from products p
join product_seasonality_profiles sp on sp.product_id = p.id
where sp.peak_months::jsonb @> '[12]'::jsonb;
```

Products missing profiles:

```sql
select p.id, p.orderpro_sku, p.name
from products p
left join product_seasonality_profiles sp on sp.product_id = p.id
where sp.id is null;
```

Products with insufficient confidence:

```sql
select p.id, p.orderpro_sku, p.name, sp.confidence_label, sp.seasonality_tag
from products p
join product_seasonality_profiles sp on sp.product_id = p.id
where sp.confidence_label in ('insufficient', 'low');
```

Products in season with low stock for June:

```sql
select p.id, p.orderpro_sku, p.name, p.current_stock, sp.monthly_indices ->> '6' as june_index
from products p
join product_seasonality_profiles sp on sp.product_id = p.id
where p.current_stock <= 0
  and (
    sp.peak_months::jsonb @> '[6]'::jsonb
    or nullif(sp.monthly_indices ->> '6', '')::numeric >= 1.2
  );
```

Products grouped by supplier and seasonality:

```sql
select s.name as supplier_name, sp.seasonality_tag, count(*) as product_count
from products p
join product_seasonality_profiles sp on sp.product_id = p.id
left join suppliers s on s.id = p.supplier_id
group by s.name, sp.seasonality_tag
order by s.name, product_count desc;
```

## Overlap and Double Counting

OrderPro current-year orders are useful for recent operational demand, but they are not used to define recurring annual seasonality in this task. Historical Excel-derived `usage_history` is the primary source.

If OrderPro order history later overlaps with historical sheets, a future backtesting task must define a cutover or de-duplication rule before combining them.

## Next Phase

Backtesting should compare seasonality profiles against actual historical stockout/reorder outcomes before seasonality is allowed to influence order quantities.
