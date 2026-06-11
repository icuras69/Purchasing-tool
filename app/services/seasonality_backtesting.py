from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.product import Product
from app.models.product_seasonality_backtest import ProductSeasonalityBacktest
from app.models.usage_history import UsageHistory
from app.services.forecasting import build_forecast
from app.services.forecast_input_reconciliation import effective_forecast_inputs, forecast_input_audit
from app.services.historical_product_reconciliation import confirmed_links_for_products
from app.services.seasonality import collect_contributing_usage_rows, is_orderpro_catalog_product, utc_now
from app.services.supplier_assignment_review import suggest_supplier_for_product


BACKTEST_VERSION = "seasonality-backtest-v1"
MIN_TRAINING_MONTHS = 12
MIN_TEST_MONTHS = 3
MAX_SEASONAL_MULTIPLIER = 2.0
MIN_SEASONAL_MULTIPLIER = 0.5


@dataclass
class BacktestPlan:
    mode: str
    backtest_version: str
    results: list[dict[str, Any]]
    products_evaluated: int
    products_skipped: int
    readiness_counts: dict[str, int]
    aggregate_metrics: dict[str, Any]
    largest_improvements: list[dict[str, Any]]
    worst_performers: list[dict[str, Any]]
    warnings: list[str]


def _month_key(value: date) -> tuple[int, int]:
    return value.year, value.month


def _quantity(row: UsageHistory) -> float:
    return float(row.net_qty if row.net_qty is not None else row.qty_used or 0)


def _monthly_totals(rows: list[UsageHistory]) -> dict[tuple[int, int], float]:
    totals: dict[tuple[int, int], float] = defaultdict(float)
    for row in rows:
        if row.date is None:
            continue
        totals[_month_key(row.date)] += _quantity(row)
    return dict(totals)


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _safe_wape(total_abs_error: float, total_actual: float) -> float | None:
    if total_actual <= 0:
        return None
    return round(total_abs_error / total_actual, 4)


def _seasonal_indices(training_totals: dict[tuple[int, int], float]) -> dict[int, float]:
    by_month: dict[int, list[float]] = defaultdict(list)
    for (_, month), quantity in training_totals.items():
        by_month[month].append(max(quantity, 0.0))
    month_averages = {month: _average(values) for month, values in by_month.items() if values}
    overall = _average(list(month_averages.values()))
    if overall <= 0:
        return {}
    return {
        month: min(max(round(value / overall, 4), MIN_SEASONAL_MULTIPLIER), MAX_SEASONAL_MULTIPLIER)
        for month, value in month_averages.items()
    }


def _evaluate_window(
    monthly_totals: dict[tuple[int, int], float],
    *,
    train_end_year: int,
    test_year: int,
) -> dict[str, Any] | None:
    training = {
        key: quantity
        for key, quantity in monthly_totals.items()
        if key[0] <= train_end_year
    }
    testing = {
        key: quantity
        for key, quantity in monthly_totals.items()
        if key[0] == test_year
    }
    if len(training) < MIN_TRAINING_MONTHS or len(testing) < MIN_TEST_MONTHS:
        return None

    training_positive = [max(quantity, 0.0) for quantity in training.values()]
    baseline = _average(training_positive)
    indices = _seasonal_indices(training)
    if baseline <= 0 or not indices:
        return None

    month_rows = []
    for (year, month), actual_raw in sorted(testing.items()):
        actual = max(actual_raw, 0.0)
        seasonal_multiplier = indices.get(month, 1.0)
        baseline_prediction = baseline
        seasonal_prediction = baseline * seasonal_multiplier
        month_rows.append(
            {
                "year": year,
                "month": month,
                "actual_units": round(actual, 4),
                "raw_actual_units": round(actual_raw, 4),
                "baseline_predicted_units": round(baseline_prediction, 4),
                "seasonal_predicted_units": round(seasonal_prediction, 4),
                "baseline_absolute_error": round(abs(actual - baseline_prediction), 4),
                "seasonal_absolute_error": round(abs(actual - seasonal_prediction), 4),
                "seasonal_multiplier": round(seasonal_multiplier, 4),
            }
        )

    return {
        "train_end_year": train_end_year,
        "test_year": test_year,
        "training_months": len(training),
        "test_months": len(testing),
        "seasonal_indices": indices,
        "monthly_results": month_rows,
    }


def _status_from_metrics(
    *,
    evaluated_months: int,
    evaluated_years: int,
    improvement_percent: float | None,
    seasonal_wape: float | None,
) -> str:
    if evaluated_months < MIN_TEST_MONTHS or evaluated_years < 1 or improvement_percent is None:
        return "insufficient_data"
    if improvement_percent >= 15 and evaluated_months >= 12 and evaluated_years >= 2:
        return "validated"
    if improvement_percent >= 8:
        return "promising"
    if improvement_percent <= -8:
        return "harmful"
    if seasonal_wape is None:
        return "insufficient_data"
    return "neutral"


def _activation_recommendation(status: str, profile_confidence: str | None) -> str:
    if status == "validated" and profile_confidence in {"medium", "high"}:
        return "candidate_for_future_adjustment"
    if status == "harmful":
        return "do_not_apply_seasonality"
    if status in {"validated", "promising", "neutral"}:
        return "safe_for_advisory_only"
    return "insufficient_evidence"


def backtest_product(
    db: Session,
    product: Product,
    *,
    test_year: int | None = None,
    backtest_version: str = BACKTEST_VERSION,
) -> dict[str, Any]:
    links = confirmed_links_for_products(db, [product.id])
    usage_rows, contribution = collect_contributing_usage_rows(db, product, links)
    monthly_totals = _monthly_totals(usage_rows)
    if not monthly_totals:
        return _insufficient_result(product, contribution, backtest_version, "No reconciled historical usage rows.")

    available_years = sorted({year for year, _ in monthly_totals})
    windows = []
    candidate_windows = [(2023, 2024), (2024, 2025)]
    if test_year is not None:
        candidate_windows = [(test_year - 1, test_year)]
    for train_end_year, window_test_year in candidate_windows:
        if train_end_year not in available_years or window_test_year not in available_years:
            continue
        window = _evaluate_window(monthly_totals, train_end_year=train_end_year, test_year=window_test_year)
        if window:
            windows.append(window)

    if not windows:
        return _insufficient_result(product, contribution, backtest_version, "Not enough train/test monthly history.")

    month_rows = [row for window in windows for row in window["monthly_results"]]
    total_actual = sum(row["actual_units"] for row in month_rows)
    baseline_abs_error = sum(row["baseline_absolute_error"] for row in month_rows)
    seasonal_abs_error = sum(row["seasonal_absolute_error"] for row in month_rows)
    baseline_predicted = sum(row["baseline_predicted_units"] for row in month_rows)
    seasonal_predicted = sum(row["seasonal_predicted_units"] for row in month_rows)
    evaluated_months = len(month_rows)
    evaluated_years = len({row["year"] for row in month_rows})
    baseline_wape = _safe_wape(baseline_abs_error, total_actual)
    seasonal_wape = _safe_wape(seasonal_abs_error, total_actual)
    improvement_percent = None
    if baseline_abs_error > 0:
        improvement_percent = round(((baseline_abs_error - seasonal_abs_error) / baseline_abs_error) * 100, 2)
    elif seasonal_abs_error == 0:
        improvement_percent = 0.0
    else:
        improvement_percent = -100.0

    readiness_status = _status_from_metrics(
        evaluated_months=evaluated_months,
        evaluated_years=evaluated_years,
        improvement_percent=improvement_percent,
        seasonal_wape=seasonal_wape,
    )
    profile = product.seasonality_profile

    return {
        "product_id": product.id,
        "orderpro_sku": product.orderpro_sku,
        "product_name": product.name,
        "readiness_status": readiness_status,
        "activation_recommendation": _activation_recommendation(
            readiness_status,
            profile.confidence_label if profile else None,
        ),
        "seasonal_improvement_percent": improvement_percent,
        "baseline_wape": baseline_wape,
        "seasonal_wape": seasonal_wape,
        "baseline_mae": round(baseline_abs_error / evaluated_months, 4) if evaluated_months else None,
        "seasonal_mae": round(seasonal_abs_error / evaluated_months, 4) if evaluated_months else None,
        "baseline_bias": round(baseline_predicted - total_actual, 4),
        "seasonal_bias": round(seasonal_predicted - total_actual, 4),
        "evaluated_months": evaluated_months,
        "evaluated_years": evaluated_years,
        "recommended_max_multiplier": _recommended_max_multiplier(readiness_status, month_rows),
        "actual_units": round(total_actual, 4),
        "baseline_predicted_units": round(baseline_predicted, 4),
        "seasonal_predicted_units": round(seasonal_predicted, 4),
        "baseline_absolute_error": round(baseline_abs_error, 4),
        "seasonal_absolute_error": round(seasonal_abs_error, 4),
        "windows": windows,
        "contribution": contribution,
        "skip_reason": None,
        "backtest_version": backtest_version,
    }


def _recommended_max_multiplier(status: str, month_rows: list[dict[str, Any]]) -> float | None:
    if status not in {"validated", "promising"}:
        return None
    return round(min(max((row["seasonal_multiplier"] for row in month_rows), default=1.0), MAX_SEASONAL_MULTIPLIER), 4)


def _insufficient_result(
    product: Product,
    contribution: dict[str, Any],
    backtest_version: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "product_id": product.id,
        "orderpro_sku": product.orderpro_sku,
        "product_name": product.name,
        "readiness_status": "insufficient_data",
        "activation_recommendation": "insufficient_evidence",
        "seasonal_improvement_percent": None,
        "baseline_wape": None,
        "seasonal_wape": None,
        "baseline_mae": None,
        "seasonal_mae": None,
        "baseline_bias": None,
        "seasonal_bias": None,
        "evaluated_months": 0,
        "evaluated_years": 0,
        "recommended_max_multiplier": None,
        "actual_units": 0.0,
        "baseline_predicted_units": 0.0,
        "seasonal_predicted_units": 0.0,
        "baseline_absolute_error": 0.0,
        "seasonal_absolute_error": 0.0,
        "windows": [],
        "contribution": contribution,
        "skip_reason": reason,
        "backtest_version": backtest_version,
    }


def build_backtest_plan(
    db: Session,
    *,
    product_id: int | None = None,
    test_year: int | None = None,
    backtest_version: str = BACKTEST_VERSION,
) -> BacktestPlan:
    query = db.query(Product).options(
        selectinload(Product.usage_history),
        selectinload(Product.seasonality_profile),
        selectinload(Product.seasonality_backtests),
    )
    query = query.filter(
        (Product.source_system == "orderpro")
        | (Product.orderpro_id.is_not(None))
        | (Product.orderpro_sku.is_not(None))
    )
    if product_id is not None:
        query = query.filter(Product.id == product_id)
    products = query.order_by(Product.id.asc()).all()
    results = [
        backtest_product(db, product, test_year=test_year, backtest_version=backtest_version)
        for product in products
    ]
    counts = Counter(result["readiness_status"] for result in results)
    aggregate = _aggregate_results(results)
    evaluated = [result for result in results if result["evaluated_months"] > 0]
    best = sorted(
        evaluated,
        key=lambda result: result["seasonal_improvement_percent"] if result["seasonal_improvement_percent"] is not None else -9999,
        reverse=True,
    )[:10]
    worst = sorted(
        evaluated,
        key=lambda result: result["seasonal_improvement_percent"] if result["seasonal_improvement_percent"] is not None else 9999,
    )[:10]
    return BacktestPlan(
        mode="dry-run",
        backtest_version=backtest_version,
        results=results,
        products_evaluated=len(evaluated),
        products_skipped=len(results) - len(evaluated),
        readiness_counts=dict(counts),
        aggregate_metrics=aggregate,
        largest_improvements=[_summary_row(result) for result in best],
        worst_performers=[_summary_row(result) for result in worst],
        warnings=[
            "Backtest results are advisory only and do not alter forecast quantities, reorder points, or purchase orders."
        ],
    )


def _summary_row(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": result["product_id"],
        "orderpro_sku": result["orderpro_sku"],
        "product_name": result["product_name"],
        "readiness_status": result["readiness_status"],
        "seasonal_improvement_percent": result["seasonal_improvement_percent"],
        "baseline_wape": result["baseline_wape"],
        "seasonal_wape": result["seasonal_wape"],
        "evaluated_months": result["evaluated_months"],
    }


def _aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [result for result in results if result["evaluated_months"] > 0]
    total_actual = sum(result["actual_units"] for result in evaluated)
    baseline_error = sum(result["baseline_absolute_error"] for result in evaluated)
    seasonal_error = sum(result["seasonal_absolute_error"] for result in evaluated)
    improvement = None
    if baseline_error > 0:
        improvement = round(((baseline_error - seasonal_error) / baseline_error) * 100, 2)
    elif seasonal_error == 0:
        improvement = 0.0
    else:
        improvement = -100.0
    return {
        "evaluated_product_count": len(evaluated),
        "actual_units": round(total_actual, 4),
        "baseline_absolute_error": round(baseline_error, 4),
        "seasonal_absolute_error": round(seasonal_error, 4),
        "baseline_wape": _safe_wape(baseline_error, total_actual),
        "seasonal_wape": _safe_wape(seasonal_error, total_actual),
        "overall_improvement_percent": improvement,
    }


def apply_backtest_results(
    db: Session,
    *,
    product_id: int | None = None,
    test_year: int | None = None,
    backtest_version: str = BACKTEST_VERSION,
) -> BacktestPlan:
    plan = build_backtest_plan(
        db,
        product_id=product_id,
        test_year=test_year,
        backtest_version=backtest_version,
    )
    now = utc_now()
    existing = {
        row.product_id: row
        for row in db.query(ProductSeasonalityBacktest)
        .filter(ProductSeasonalityBacktest.backtest_version == backtest_version)
        .all()
    }
    for result in plan.results:
        row = existing.get(result["product_id"])
        if row is None:
            row = ProductSeasonalityBacktest(
                product_id=result["product_id"],
                backtest_version=backtest_version,
                created_at=now,
            )
            db.add(row)
        row.readiness_status = result["readiness_status"]
        row.activation_recommendation = result["activation_recommendation"]
        row.seasonal_improvement_percent = result["seasonal_improvement_percent"]
        row.baseline_wape = result["baseline_wape"]
        row.seasonal_wape = result["seasonal_wape"]
        row.baseline_mae = result["baseline_mae"]
        row.seasonal_mae = result["seasonal_mae"]
        row.baseline_bias = result["baseline_bias"]
        row.seasonal_bias = result["seasonal_bias"]
        row.evaluated_months = result["evaluated_months"]
        row.evaluated_years = result["evaluated_years"]
        row.recommended_max_multiplier = result["recommended_max_multiplier"]
        row.metrics = {
            key: result[key]
            for key in (
                "actual_units",
                "baseline_predicted_units",
                "seasonal_predicted_units",
                "baseline_absolute_error",
                "seasonal_absolute_error",
                "windows",
                "contribution",
                "skip_reason",
            )
        }
        row.calculated_at = now
        row.updated_at = now
    db.commit()
    plan.mode = "apply"
    return plan


CRITICAL_INPUTS = {"supplier_id", "current_stock", "demand_history"}
ADVISORY_INPUTS = {"usable_seasonality_profile", "seasonality_backtest_result"}


def audit_product_forecast_inputs(db: Session, product: Product) -> dict[str, Any]:
    forecast_before = build_forecast(db, product)
    effective_inputs = effective_forecast_inputs(db, product)
    has_inventory_positions = bool(product.inventory_positions)
    has_orderpro_demand = bool(product.orderpro_order_items)
    links = confirmed_links_for_products(db, [product.id])
    linked_rows, _ = collect_contributing_usage_rows(db, product, links)
    has_reconciled_history = bool(linked_rows)
    profile = product.seasonality_profile
    latest_backtest = _latest_backtest(product)

    input_flags = {
        "supplier_id": product.supplier_id is not None,
        "supplier_sku": bool(product.supplier_sku),
        "current_stock": product.current_stock is not None,
        "inventory_positions": has_inventory_positions,
        "shipped_orderpro_demand": has_orderpro_demand and forecast_before.get("shipped_units_in_window", 0) > 0,
        "open_committed_demand": forecast_before.get("total_open_demand", 0) > 0,
        "reconciled_historical_demand": has_reconciled_history,
        "usable_seasonality_profile": bool(profile and profile.seasonality_tag != "insufficient_data"),
        "seasonality_backtest_result": latest_backtest is not None,
        "lead_time": effective_inputs["lead_time_days"] is not None,
        "moq": effective_inputs["min_order_qty"] is not None,
        "pack_size": effective_inputs["pack_size"] is not None,
        "safety_stock": effective_inputs["safety_stock"] is not None,
        "cost_price": effective_inputs["cost_price"] is not None,
        "active_status": bool(product.is_active),
    }

    available = sorted([name for name, present in input_flags.items() if present])
    missing = sorted([name for name, present in input_flags.items() if not present])
    currently_used = [
        "supplier_id" if input_flags["supplier_id"] else "legacy_supplier_or_missing",
        "current_stock",
        "shipped_orderpro_demand" if input_flags["shipped_orderpro_demand"] else "legacy_usage_history_or_no_history",
        "open_committed_demand",
        "lead_time" if input_flags["lead_time"] else "missing_lead_time",
        "moq",
        "safety_stock",
    ]
    advisory = [name for name in ADVISORY_INPUTS if input_flags[name]]
    blocking = []
    warnings = []
    if not input_flags["supplier_id"]:
        blocking.append("missing_supplier")
    if not input_flags["lead_time"]:
        warnings.append("missing_lead_time")
    if not input_flags["cost_price"]:
        warnings.append("missing_cost")
    if effective_inputs["moq_source"] == "business_default":
        warnings.append("fallback_moq")
    if not input_flags["pack_size"]:
        warnings.append("missing_pack_size")
    if not (input_flags["shipped_orderpro_demand"] or input_flags["reconciled_historical_demand"]):
        warnings.append("missing_demand_history")
    if latest_backtest and latest_backtest.readiness_status == "harmful":
        warnings.append("seasonality_backtest_harmful")

    supplier_suggestion = None
    if not input_flags["supplier_id"]:
        suggestion = suggest_supplier_for_product(db, product)
        if suggestion["suggested_supplier_id"] is not None:
            warnings.append("supplier_assignment_suggestion_available")
            supplier_suggestion = {
                "suggested_supplier_id": suggestion["suggested_supplier_id"],
                "suggested_supplier_name": suggestion["suggested_supplier_name"],
                "suggestion_source": suggestion["suggestion_source"],
                "confidence_label": suggestion["confidence_label"],
                "confidence_score": suggestion["confidence_score"],
            }

    score = round((len(available) / len(input_flags)) * 100, 2)
    return {
        "product_id": product.id,
        "orderpro_sku": product.orderpro_sku,
        "product_name": product.name,
        "available_inputs": available,
        "missing_inputs": missing,
        "inputs_currently_used": currently_used,
        "advisory_inputs": sorted(advisory),
        "blocking_issues": blocking,
        "warning_issues": warnings,
        "forecast_readiness_score": score,
        "cost_price": effective_inputs["cost_price"],
        "cost_source": effective_inputs["cost_source"],
        "cost_confidence": effective_inputs["cost_confidence"],
        "lead_time_days": effective_inputs["lead_time_days"],
        "lead_time_source": effective_inputs["lead_time_source"],
        "lead_time_confidence": effective_inputs["lead_time_confidence"],
        "min_order_qty": effective_inputs["min_order_qty"],
        "moq_source": effective_inputs["moq_source"],
        "pack_size": effective_inputs["pack_size"],
        "pack_size_source": effective_inputs["pack_size_source"],
        "safety_stock": effective_inputs["safety_stock"],
        "safety_stock_source": effective_inputs["safety_stock_source"],
        "seasonality_activation_recommendation": (
            latest_backtest.activation_recommendation if latest_backtest else "insufficient_evidence"
        ),
        "seasonality_readiness_status": latest_backtest.readiness_status if latest_backtest else None,
        "forecast_recommended_qty": forecast_before["recommended_qty"],
        "supplier_assignment_suggestion": supplier_suggestion,
    }


def _latest_backtest(product: Product) -> ProductSeasonalityBacktest | None:
    if not product.seasonality_backtests:
        return None
    return sorted(product.seasonality_backtests, key=lambda row: row.calculated_at, reverse=True)[0]


def forecast_readiness_summary(db: Session) -> dict[str, Any]:
    products = (
        db.query(Product)
        .options(
            selectinload(Product.inventory_positions),
            selectinload(Product.orderpro_order_items),
            selectinload(Product.seasonality_profile),
            selectinload(Product.seasonality_backtests),
            selectinload(Product.supplier_record),
        )
        .filter(
            (Product.source_system == "orderpro")
            | (Product.orderpro_id.is_not(None))
            | (Product.orderpro_sku.is_not(None))
        )
        .all()
    )
    audits = [audit_product_forecast_inputs(db, product) for product in products]
    input_audit = forecast_input_audit(db, products=products)
    return {
        "product_count": len(products),
        "products_with_complete_critical_inputs": sum(
            1 for audit in audits if not any(issue == "missing_supplier" for issue in audit["blocking_issues"])
        ),
        "products_missing_supplier": sum(1 for audit in audits if "missing_supplier" in audit["blocking_issues"]),
        "products_missing_lead_time": sum(1 for audit in audits if "missing_lead_time" in audit["warning_issues"]),
        "products_missing_cost": sum(1 for audit in audits if "missing_cost" in audit["warning_issues"]),
        "products_missing_moq": sum(1 for audit in audits if audit["moq_source"] == "missing"),
        "products_missing_pack_size": sum(1 for audit in audits if "missing_pack_size" in audit["warning_issues"]),
        "products_using_fallback_moq": sum(1 for audit in audits if audit["moq_source"] == "business_default"),
        "products_using_po_derived_cost": sum(
            1
            for audit in audits
            if audit["cost_source"] in {"orderpro_purchase_order_line", "local_purchase_order_line"}
        ),
        "products_using_orderpro_cost": sum(1 for audit in audits if audit["cost_source"] == "orderpro_product_cost"),
        "suppliers_missing_lead_time": input_audit["suppliers_missing_lead_time"],
        "products_blocked_by_missing_supplier": sum(1 for audit in audits if "missing_supplier" in audit["blocking_issues"]),
        "products_blocked_by_missing_demand": sum(
            1 for audit in audits if "missing_demand_history" in audit["warning_issues"]
        ),
        "products_complete_before_reconciliation": sum(
            1
            for product in products
            if product.supplier_id is not None
            and product.cost_price is not None
            and (
                (product.lead_time_days and product.lead_time_days > 0)
                or (product.supplier_record and product.supplier_record.lead_time_days)
            )
        ),
        "products_complete_after_reconciliation": sum(
            1
            for audit in audits
            if "missing_supplier" not in audit["blocking_issues"]
            and "missing_cost" not in audit["warning_issues"]
            and "missing_lead_time" not in audit["warning_issues"]
        ),
        "products_missing_demand_history": sum(
            1 for audit in audits if "missing_demand_history" in audit["warning_issues"]
        ),
        "products_missing_seasonality": sum(
            1 for audit in audits if "usable_seasonality_profile" in audit["missing_inputs"]
        ),
        "products_with_validated_seasonality": sum(
            1 for audit in audits if audit["seasonality_readiness_status"] == "validated"
        ),
        "products_with_harmful_seasonality": sum(
            1 for audit in audits if audit["seasonality_readiness_status"] == "harmful"
        ),
    }


def list_forecast_readiness(db: Session, *, filter_name: str | None = None) -> list[dict[str, Any]]:
    products = (
        db.query(Product)
        .options(
            selectinload(Product.inventory_positions),
            selectinload(Product.orderpro_order_items),
            selectinload(Product.seasonality_profile),
            selectinload(Product.seasonality_backtests),
            selectinload(Product.supplier_record),
        )
        .filter(
            (Product.source_system == "orderpro")
            | (Product.orderpro_id.is_not(None))
            | (Product.orderpro_sku.is_not(None))
        )
        .order_by(Product.id.asc())
        .all()
    )
    audits = [audit_product_forecast_inputs(db, product) for product in products]
    if filter_name == "missing_supplier":
        audits = [audit for audit in audits if "missing_supplier" in audit["blocking_issues"]]
    elif filter_name == "missing_lead_time":
        audits = [audit for audit in audits if "missing_lead_time" in audit["warning_issues"]]
    elif filter_name == "missing_cost":
        audits = [audit for audit in audits if "missing_cost" in audit["warning_issues"]]
    elif filter_name == "missing_moq":
        audits = [audit for audit in audits if audit["moq_source"] == "missing"]
    elif filter_name == "missing_pack_size":
        audits = [audit for audit in audits if "missing_pack_size" in audit["warning_issues"]]
    elif filter_name == "fallback_moq":
        audits = [audit for audit in audits if audit["moq_source"] == "business_default"]
    elif filter_name == "po_derived_cost":
        audits = [
            audit
            for audit in audits
            if audit["cost_source"] in {"orderpro_purchase_order_line", "local_purchase_order_line"}
        ]
    elif filter_name == "ready_for_forecast":
        audits = [
            audit
            for audit in audits
            if "missing_supplier" not in audit["blocking_issues"]
            and "missing_cost" not in audit["warning_issues"]
            and "missing_lead_time" not in audit["warning_issues"]
        ]
    elif filter_name == "incomplete_critical_inputs":
        audits = [
            audit
            for audit in audits
            if "missing_supplier" in audit["blocking_issues"]
            or "missing_cost" in audit["warning_issues"]
            or "missing_lead_time" in audit["warning_issues"]
        ]
    elif filter_name == "no_demand_history":
        audits = [audit for audit in audits if "missing_demand_history" in audit["warning_issues"]]
    elif filter_name == "seasonal_validated":
        audits = [audit for audit in audits if audit["seasonality_readiness_status"] == "validated"]
    elif filter_name == "seasonal_harmful":
        audits = [audit for audit in audits if audit["seasonality_readiness_status"] == "harmful"]
    elif filter_name:
        raise ValueError("Invalid readiness filter.")
    return audits
