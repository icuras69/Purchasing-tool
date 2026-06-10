# Seasonality Backtesting

Seasonality remains advisory. This backtest measures whether historical seasonal
indices would have improved monthly demand prediction, but it does not change
forecast recommended quantities, reorder points, purchase order quantities, or
purchase order workflow state.

## Data Source

Backtesting uses the same reconciled historical `usage_history` rows as the
seasonality profile calculation:

- direct `usage_history` rows on the current OrderPro product, if any;
- `usage_history` rows from `ProductHistoricalLink` records with status
  `auto_confirmed` or `manually_confirmed`;
- ambiguous, `needs_review`, and `rejected` links are excluded.

Each usage row is counted once. OrderPro API calls are not made during
backtesting.

## Train/Test Split

The default walk-forward windows are:

- train through 2023, test on 2024;
- train through 2024, test on available 2025 months.

Training windows use only months at or before the training cutoff. Test-period
actuals are never used to calculate seasonal indices, which prevents future-data
leakage.

## Baseline Method

The baseline prediction is the average positive monthly quantity in the training
period. Negative monthly totals are retained as raw audit evidence, but monthly
test actuals are clamped to zero for error calculations so returns do not create
misleading negative demand percentages.

## Seasonal Method

The seasonal candidate multiplies the baseline by a calendar-month seasonal
index calculated from training data only:

```text
seasonal_prediction = trailing_monthly_average * training_month_seasonal_index
```

Seasonal multipliers are capped between `0.5` and `2.0` for the backtest so one
extreme historical month cannot imply an unbounded future adjustment.

## Metrics

Per product and aggregate reports include:

- actual units;
- baseline predicted units;
- seasonal predicted units;
- absolute error;
- MAE;
- WAPE, when actual demand is greater than zero;
- bias;
- improvement percent;
- evaluated months and years.

WAPE is omitted when actual demand is zero rather than reporting a misleading
percentage.

## Readiness Status

Backtesting stores one advisory readiness status per product:

- `validated`: seasonal method materially improves error with at least two test
  years and enough evaluated months;
- `promising`: seasonal method improves error, but evidence is more limited;
- `neutral`: little meaningful difference;
- `harmful`: seasonal adjustment worsens error materially;
- `insufficient_data`: not enough train/test history or no meaningful actual
  demand.

Readiness depends on measured backtest performance and coverage, not on
seasonality confidence alone.

## Activation Recommendation

The service also stores an advisory activation recommendation:

- `candidate_for_future_adjustment`;
- `safe_for_advisory_only`;
- `do_not_apply_seasonality`;
- `insufficient_evidence`.

No product is automatically activated for seasonal quantity adjustment. Future
activation would require a separate implementation, review, and tests proving PO
and forecast behavior remains safe.

## Forecast Input Coverage

Forecast readiness APIs report which inputs are available, currently used, or
advisory:

- supplier assignment;
- supplier SKU;
- current stock;
- inventory positions;
- shipped OrderPro demand;
- open committed demand;
- reconciled historical demand;
- usable seasonality profile;
- seasonality backtest result;
- lead time;
- MOQ;
- pack size;
- safety stock;
- cost price;
- active status.

The audit does not claim seasonality is currently used for purchase quantities.
Seasonality and backtest results remain advisory inputs only.

## Commands

Dry-run:

```powershell
python scripts/backtest_product_seasonality.py --dry-run --save-report
```

Apply backtest results only:

```powershell
python scripts/backtest_product_seasonality.py --apply --save-report
```

Run for one product:

```powershell
python scripts/backtest_product_seasonality.py --dry-run --product-id 7832 --save-report
```

Forecast readiness:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/forecast-readiness/summary
Invoke-RestMethod http://127.0.0.1:8000/products/7832/forecast-readiness
Invoke-RestMethod "http://127.0.0.1:8000/products/forecast-readiness?filter=missing_lead_time"
```
