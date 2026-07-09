from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.orderpro_order import OrderProOrder, OrderProOrderItem
from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.recommendation import Recommendation
from app.models.usage_history import UsageHistory
from app.services.forecast_input_reconciliation import profile_or_effective_inputs
from app.services.forecasting import build_forecast


ACTIONABLE_RECOMMENDATION_STATUSES = {"draft", "pending_review", "accepted"}


def load_product_for_recommendation_explanation(db: Session, product_id: int) -> Product | None:
    return (
        db.query(Product)
        .options(
            selectinload(Product.supplier_record),
            selectinload(Product.product_suppliers).selectinload(ProductSupplier.supplier),
            selectinload(Product.inventory_positions),
            selectinload(Product.forecast_input_profile),
        )
        .filter(Product.id == product_id)
        .first()
    )


def explain_product_recommendation(
    db: Session,
    product_id: int,
    *,
    today: date | None = None,
) -> dict[str, Any] | None:
    product = load_product_for_recommendation_explanation(db, product_id)
    if product is None:
        return None

    forecast = build_forecast(db, product)
    effective_inputs = profile_or_effective_inputs(db, product)
    demand = demand_summary(db, product, forecast)
    today_value = today or datetime.now(timezone.utc).date()
    recommended_qty = float(forecast.get("recommended_qty") or 0)
    current_stock = forecast.get("current_stock")
    lead_time_days = effective_inputs.get("lead_time_days")
    minimum_order_quantity = effective_inputs.get("min_order_qty")
    supplier = product.supplier_record

    blockers = blockers_for_product(product, effective_inputs, forecast, demand)
    warnings = warnings_for_product(effective_inputs, forecast, demand, today_value)
    status = explanation_status(blockers, forecast, recommended_qty)
    reasons = reasons_for_product(product, forecast, demand, blockers, status)
    suspicious_issues = suspicious_issues_for_explanation(
        status=status,
        blockers=blockers,
        warnings=warnings,
        forecast=forecast,
        recommended_quantity=recommended_qty,
        minimum_order_quantity=minimum_order_quantity,
    )

    return {
        "product_id": product.id,
        "orderpro_sku": product.orderpro_sku,
        "product_name": product.name,
        "supplier_id": product.supplier_id,
        "supplier_name": supplier.name if supplier else None,
        "supplier_source": "products.supplier_id" if product.supplier_id and supplier else "missing",
        "current_stock": current_stock,
        "inventory_source": forecast.get("inventory_source"),
        "demand_source": forecast.get("demand_source"),
        "demand_quantity_mode": forecast.get("legacy_demand_quantity_mode"),
        "demand_policy_status": forecast.get("demand_policy_status"),
        "stale_demand_only": bool(forecast.get("stale_demand_only")),
        "stale_demand_policy": stale_demand_policy_status(forecast),
        "legacy_demand_raw_units_in_window": forecast.get("legacy_demand_raw_units_in_window"),
        "legacy_demand_negative_or_return_rows": forecast.get("legacy_demand_negative_or_return_rows"),
        "demand_rows": demand["demand_rows"],
        "last_demand_date": iso_date(demand["last_demand_date"]),
        "recent_demand_units": demand["recent_demand_units"],
        "open_customer_demand": forecast.get("total_open_demand"),
        "average_daily_demand": forecast.get("avg_daily_usage"),
        "monthly_average_demand": monthly_average(forecast.get("avg_daily_usage")),
        "lead_time_days": lead_time_days,
        "lead_time_source": effective_inputs.get("lead_time_source"),
        "days_of_cover": forecast.get("days_until_stockout"),
        "reorder_point": forecast.get("reorder_point"),
        "minimum_order_quantity": minimum_order_quantity,
        "moq_source": effective_inputs.get("moq_source"),
        "incoming_qty": forecast.get("incoming_qty"),
        "recommended_action": forecast.get("recommended_action"),
        "recommended_quantity": recommended_qty,
        "recommended_quantity_before_inbound": forecast.get("recommended_qty_before_inbound"),
        "recommended_quantity_after_inbound": forecast.get("recommended_qty_after_inbound"),
        "reason": forecast.get("explanation"),
        "status": status,
        "confidence": confidence_label(blockers, warnings),
        "readiness_status": readiness_status_for_explanation(status, blockers),
        "readiness_score": forecast.get("forecast_readiness_score"),
        "reasons": reasons,
        "blockers": blockers,
        "warnings": warnings,
        "suspicious_issues": suspicious_issues,
        "forecast_snapshot": forecast,
    }


def demand_summary(db: Session, product: Product, forecast: dict[str, Any]) -> dict[str, Any]:
    usage_count = db.query(func.count(UsageHistory.id)).filter(UsageHistory.product_id == product.id).scalar() or 0
    latest_usage_date = db.query(func.max(UsageHistory.date)).filter(UsageHistory.product_id == product.id).scalar()
    negative_usage_rows = (
        db.query(func.count(UsageHistory.id))
        .filter(UsageHistory.product_id == product.id)
        .filter(
            (UsageHistory.qty_used < 0)
            | (UsageHistory.net_qty < 0)
            | (UsageHistory.qty_returned > 0)
        )
        .scalar()
        or 0
    )

    orderpro_latest = (
        db.query(func.max(OrderProOrder.order_date))
        .join(OrderProOrderItem, OrderProOrderItem.order_id == OrderProOrder.id)
        .filter(OrderProOrderItem.product_id == product.id)
        .filter(func.lower(OrderProOrder.status) == "shipped")
        .scalar()
    )
    orderpro_line_count = (
        db.query(func.count(OrderProOrderItem.id))
        .join(OrderProOrder, OrderProOrder.id == OrderProOrderItem.order_id)
        .filter(OrderProOrderItem.product_id == product.id)
        .filter(func.lower(OrderProOrder.status) == "shipped")
        .scalar()
        or 0
    )
    orderpro_negative_rows = (
        db.query(func.count(OrderProOrderItem.id))
        .join(OrderProOrder, OrderProOrder.id == OrderProOrderItem.order_id)
        .filter(OrderProOrderItem.product_id == product.id)
        .filter(
            (OrderProOrderItem.quantity < 0)
            | (OrderProOrderItem.quantity_ordered < 0)
            | (OrderProOrderItem.quantity_shipped < 0)
        )
        .scalar()
        or 0
    )

    forecast_end = forecast.get("demand_history_end")
    last_demand_date = max_present_dates([forecast_end, latest_usage_date, order_date(orderpro_latest)])
    demand_rows = int(forecast.get("eligible_order_count") or 0)
    if forecast.get("demand_source") == "usage_history":
        demand_rows = int(usage_count)
    elif orderpro_line_count:
        demand_rows = int(orderpro_line_count)

    return {
        "demand_rows": demand_rows,
        "last_demand_date": last_demand_date,
        "recent_demand_units": float(forecast.get("units_sold_in_window") or forecast.get("shipped_units_in_window") or 0),
        "has_demand_history": demand_rows > 0 or float(forecast.get("units_sold_in_window") or 0) > 0,
        "negative_or_return_rows": int(negative_usage_rows + orderpro_negative_rows),
    }


def blockers_for_product(
    product: Product,
    effective_inputs: dict[str, Any],
    forecast: dict[str, Any],
    demand: dict[str, Any],
) -> list[str]:
    blockers = []
    if product.is_non_inventory:
        blockers.append("Product is non-inventory")
    if product.supplier_id is None or product.supplier_record is None:
        blockers.append("Missing supplier")
    if product.current_stock is None:
        blockers.append("Missing current stock")
    if not demand["has_demand_history"] and float(forecast.get("total_open_demand") or 0) <= 0:
        blockers.append("No demand history")
    lead_time_days = effective_inputs.get("lead_time_days")
    if lead_time_days is None or lead_time_days <= 0:
        blockers.append("Missing lead time")
    return blockers


def warnings_for_product(
    effective_inputs: dict[str, Any],
    forecast: dict[str, Any],
    demand: dict[str, Any],
    today: date,
) -> list[str]:
    warnings = []
    last_demand_date = demand["last_demand_date"]
    stale_days = int(forecast.get("legacy_demand_stale_days") or settings.legacy_demand_stale_days)
    if last_demand_date and (today - last_demand_date).days > stale_days and float(forecast.get("total_open_demand") or 0) <= 0:
        warnings.append(f"Stale demand only; last demand is older than {stale_days} days")
    if demand["negative_or_return_rows"]:
        warnings.append("Demand history includes returns or negative quantities")
    if forecast.get("legacy_demand_negative_or_return_rows"):
        warnings.append("Returns or negative rows affected legacy demand calculation")
    if "missing_cost" in effective_inputs.get("warning_issues", []):
        warnings.append("Missing cost")
    if "fallback_moq" in effective_inputs.get("warning_issues", []):
        warnings.append("Using fallback MOQ")
    if "missing_pack_size" in effective_inputs.get("warning_issues", []):
        warnings.append("Missing pack size")
    if forecast.get("recommended_action") == "monitor" and float(forecast.get("incoming_qty") or 0) > 0:
        warnings.append("Incoming stock covers the current shortfall")
    return warnings


def explanation_status(blockers: list[str], forecast: dict[str, Any], recommended_qty: float) -> str:
    if blockers:
        return "blocked"
    if is_stale_demand_only(forecast) and not settings.allow_stale_demand_recommendations and recommended_qty > 0:
        return "needs_review"
    if forecast.get("recommended_action") == "reorder" and recommended_qty > 0:
        return "actionable"
    return "monitor"


def readiness_status_for_explanation(status: str, blockers: list[str]) -> str:
    if blockers:
        return "blocked"
    if status == "actionable":
        return "ready"
    if status == "needs_review":
        return "partially_ready"
    return "monitor_only"


def is_stale_demand_only(forecast: dict[str, Any]) -> bool:
    return (
        forecast.get("demand_source") == "usage_history"
        and bool(forecast.get("stale_demand_only"))
        and float(forecast.get("total_open_demand") or 0) <= 0
    )


def stale_demand_policy_status(forecast: dict[str, Any]) -> str:
    if not is_stale_demand_only(forecast):
        return "recent_or_not_legacy"
    if settings.allow_stale_demand_recommendations:
        return "allowed_by_config_with_warning"
    return "manual_review_required"


def reasons_for_product(
    product: Product,
    forecast: dict[str, Any],
    demand: dict[str, Any],
    blockers: list[str],
    status: str,
) -> list[str]:
    reasons = []
    if product.supplier_id and product.supplier_record:
        reasons.append(f"Product has supplier assigned: {product.supplier_record.name}")
    if demand["has_demand_history"]:
        reasons.append(
            f"Product has demand history: {demand['demand_rows']} rows and {demand['recent_demand_units']} recent units"
        )
    if forecast.get("avg_daily_usage"):
        reasons.append(f"Average monthly demand is {monthly_average(forecast.get('avg_daily_usage'))}")
    lead_time = forecast.get("lead_time_days_used")
    if lead_time and lead_time > 0:
        reasons.append(f"Supplier lead time is {lead_time} days")
    if status == "actionable":
        reasons.append("Current stock is below projected demand, open demand, or safety stock requirements")
        reasons.append(f"Recommended reorder quantity is {forecast.get('recommended_qty')}")
    elif status == "needs_review":
        reasons.append("Calculated reorder quantity is advisory because the only demand signal is stale legacy demand")
    elif status == "monitor" and not blockers:
        reasons.append("Current stock and inbound stock are sufficient for the forecast inputs")
    return reasons


def suspicious_issues_for_explanation(
    *,
    status: str,
    blockers: list[str],
    warnings: list[str],
    forecast: dict[str, Any],
    recommended_quantity: float,
    minimum_order_quantity: float | None,
    recommendation_status: str | None = None,
) -> list[str]:
    issues = []
    is_actionable = status == "actionable"
    if recommendation_status is not None:
        is_actionable = recommendation_status in ACTIONABLE_RECOMMENDATION_STATUSES

    if is_actionable and "Missing supplier" in blockers:
        issues.append("Actionable recommendation is missing supplier")
    if is_actionable and "No demand history" in blockers:
        issues.append("Actionable recommendation has no demand history")
    if is_actionable and any(warning.startswith("Stale demand only") for warning in warnings):
        issues.append("Actionable recommendation has stale demand only")
    if is_actionable and recommended_quantity <= 0:
        issues.append("Actionable recommendation has non-positive quantity")
    if (
        is_actionable
        and minimum_order_quantity is not None
        and minimum_order_quantity > 0
        and 0 < recommended_quantity < minimum_order_quantity
    ):
        issues.append("Recommended quantity is less than MOQ")
    if is_actionable and forecast.get("recommended_action") != "reorder":
        issues.append("Actionable recommendation exists while forecast action is not reorder")
    if (
        is_actionable
        and forecast.get("recommended_action") == "reorder"
        and float(forecast.get("effective_available_stock_for_reorder") or 0) >= float(forecast.get("total_required_stock") or 0)
    ):
        issues.append("Recommendation appears to have enough stock without a clear shortfall")
    return issues


def audit_existing_recommendations(db: Session, *, limit: int = 500) -> dict[str, Any]:
    recommendations = (
        db.query(Recommendation)
        .options(
            selectinload(Recommendation.product).selectinload(Product.supplier_record),
            selectinload(Recommendation.product).selectinload(Product.product_suppliers),
        )
        .order_by(Recommendation.id.asc())
        .limit(limit)
        .all()
    )
    items = []
    issue_counter: Counter[str] = Counter()
    for recommendation in recommendations:
        explanation = explain_product_recommendation(db, recommendation.product_id)
        if explanation is None:
            issues = ["Recommendation product is missing"]
            issue_counter.update(issues)
            items.append(
                {
                    "recommendation_id": recommendation.id,
                    "product_id": recommendation.product_id,
                    "status": recommendation.status,
                    "recommended_quantity": recommendation.recommended_qty,
                    "explanation_status": "blocked",
                    "suspicious_issues": issues,
                }
            )
            continue

        issues = suspicious_issues_for_explanation(
            status=explanation["status"],
            blockers=explanation["blockers"],
            warnings=explanation["warnings"],
            forecast=explanation["forecast_snapshot"],
            recommended_quantity=float(recommendation.recommended_qty or 0),
            minimum_order_quantity=explanation["minimum_order_quantity"],
            recommendation_status=recommendation.status,
        )
        issue_counter.update(issues)
        items.append(
            {
                "recommendation_id": recommendation.id,
                "product_id": recommendation.product_id,
                "product_name": explanation["product_name"],
                "supplier_id": recommendation.supplier_id,
                "supplier_name": explanation["supplier_name"],
                "status": recommendation.status,
                "recommended_quantity": recommendation.recommended_qty,
                "explanation_status": explanation["status"],
                "forecast_recommended_action": explanation["recommended_action"],
                "blockers": explanation["blockers"],
                "warnings": explanation["warnings"],
                "suspicious_issues": issues,
            }
        )

    return {
        "summary": {
            "recommendations_evaluated": len(recommendations),
            "suspicious_recommendations": sum(1 for item in items if item["suspicious_issues"]),
            "issue_counts": dict(issue_counter),
            "limit": limit,
        },
        "items": items,
    }


def demand_policy_impact(
    db: Session,
    *,
    lookback_days: int | None = None,
    quantity_mode: str | None = None,
    stale_days: int | None = None,
    limit: int = 500,
    today: date | None = None,
) -> dict[str, Any]:
    requested_quantity_mode = normalize_quantity_mode_for_audit(quantity_mode)
    effective_stale_days = stale_days or settings.legacy_demand_stale_days
    today_value = today or datetime.now(timezone.utc).date()
    recent_window = lookback_days if lookback_days is not None else 365
    products = (
        db.query(Product)
        .options(
            selectinload(Product.supplier_record),
            selectinload(Product.product_suppliers).selectinload(ProductSupplier.supplier),
            selectinload(Product.inventory_positions),
            selectinload(Product.forecast_input_profile),
        )
        .order_by(Product.id.asc())
        .limit(limit)
        .all()
    )

    items = []
    current_actionable = 0
    net_actionable = 0
    recent_actionable = 0
    stale_only_actionable = 0
    stale_only_needs_review = 0
    quantity_changes = 0
    status_changes = 0

    for product in products:
        current = policy_projection(
            db,
            product,
            quantity_mode=settings.legacy_demand_quantity_mode,
            lookback_days=settings.legacy_demand_lookback_days,
            stale_days=effective_stale_days,
            today=today_value,
        )
        net_qty = policy_projection(
            db,
            product,
            quantity_mode="net_qty",
            lookback_days=settings.legacy_demand_lookback_days,
            stale_days=effective_stale_days,
            today=today_value,
        )
        requested = policy_projection(
            db,
            product,
            quantity_mode=requested_quantity_mode,
            lookback_days=lookback_days,
            stale_days=effective_stale_days,
            today=today_value,
        )
        recent = policy_projection(
            db,
            product,
            quantity_mode=requested_quantity_mode,
            lookback_days=recent_window,
            stale_days=effective_stale_days,
            today=today_value,
        )

        current_actionable += int(current["status"] == "actionable")
        net_actionable += int(net_qty["status"] == "actionable")
        recent_actionable += int(recent["status"] == "actionable")
        stale_only_actionable += int(current["status"] == "actionable" and current["stale_demand_only"])
        stale_only_needs_review += int(current["status"] == "needs_review" and current["stale_demand_only"])
        quantity_changed = current["recommended_quantity"] != requested["recommended_quantity"]
        status_changed = current["status"] != requested["status"]
        quantity_changes += int(quantity_changed)
        status_changes += int(status_changed)
        if quantity_changed or status_changed or current["stale_demand_only"]:
            items.append(
                {
                    "product_id": product.id,
                    "product_name": product.name,
                    "supplier_id": product.supplier_id,
                    "supplier_name": product.supplier_record.name if product.supplier_record else None,
                    "current_policy": current,
                    "net_qty_policy": net_qty,
                    "requested_policy": requested,
                    "recent_window_policy": recent,
                    "quantity_changed": quantity_changed,
                    "status_changed": status_changed,
                }
            )

    return {
        "parameters": {
            "lookback_days": lookback_days,
            "quantity_mode": requested_quantity_mode,
            "stale_days": effective_stale_days,
            "limit": limit,
            "recent_window_days": recent_window,
        },
        "summary": {
            "total_products_evaluated": len(products),
            "actionable_current_policy": current_actionable,
            "actionable_using_net_qty": net_actionable,
            "actionable_using_recent_window": recent_actionable,
            "stale_only_actionable_count": stale_only_actionable,
            "stale_only_needs_review_count": stale_only_needs_review,
            "products_where_recommendation_quantity_changes": quantity_changes,
            "products_where_recommendation_status_changes": status_changes,
        },
        "examples": items[:25],
    }


def policy_projection(
    db: Session,
    product: Product,
    *,
    quantity_mode: str,
    lookback_days: int | None,
    stale_days: int,
    today: date,
) -> dict[str, Any]:
    forecast = build_forecast(
        db,
        product,
        legacy_quantity_mode=quantity_mode,
        legacy_lookback_days=lookback_days,
        legacy_stale_days=stale_days,
        today=today,
    )
    effective_inputs = profile_or_effective_inputs(db, product)
    demand = {
        "demand_rows": int(forecast.get("eligible_order_count") or 0),
        "last_demand_date": order_date(forecast.get("demand_history_end")),
        "recent_demand_units": float(forecast.get("units_sold_in_window") or forecast.get("shipped_units_in_window") or 0),
        "has_demand_history": int(forecast.get("eligible_order_count") or 0) > 0
        or float(forecast.get("units_sold_in_window") or 0) > 0,
        "negative_or_return_rows": int(forecast.get("legacy_demand_negative_or_return_rows") or 0),
    }
    blockers = blockers_for_product(product, effective_inputs, forecast, demand)
    warnings = warnings_for_product(effective_inputs, forecast, demand, today)
    recommended_quantity = float(forecast.get("recommended_qty") or 0)
    status = explanation_status(blockers, forecast, recommended_quantity)
    return {
        "status": status,
        "readiness_status": readiness_status_for_explanation(status, blockers),
        "recommended_action": forecast.get("recommended_action"),
        "recommended_quantity": recommended_quantity,
        "monthly_average_demand": monthly_average(forecast.get("avg_daily_usage")),
        "last_demand_date": iso_date(demand["last_demand_date"]),
        "demand_rows": demand["demand_rows"],
        "demand_source": forecast.get("demand_source"),
        "demand_quantity_mode": forecast.get("legacy_demand_quantity_mode"),
        "demand_lookback_days": forecast.get("demand_lookback_days"),
        "demand_policy_status": forecast.get("demand_policy_status"),
        "stale_demand_only": bool(forecast.get("stale_demand_only")),
        "blockers": blockers,
        "warnings": warnings,
    }


def normalize_quantity_mode_for_audit(quantity_mode: str | None) -> str:
    mode = (quantity_mode or settings.legacy_demand_quantity_mode or "net_qty").strip().lower()
    return mode if mode in {"net_qty", "qty_used"} else "net_qty"


def validate_product_can_create_reorder_recommendation(explanation: dict[str, Any]) -> None:
    if "Missing supplier" in explanation["blockers"]:
        raise ValueError("Product is missing a canonical supplier assignment.")
    if "Missing lead time" in explanation["blockers"]:
        raise ValueError("Product is missing usable supplier lead time.")
    if "No demand history" in explanation["blockers"]:
        raise ValueError("Product is missing demand history or open demand.")
    if explanation.get("stale_demand_only") and not settings.allow_stale_demand_recommendations:
        raise ValueError("Product has stale-only legacy demand and requires manual review.")
    if explanation["status"] != "actionable":
        raise ValueError("Product is not currently recommended for reorder.")


def monthly_average(avg_daily_usage: Any) -> float:
    try:
        return round(float(avg_daily_usage or 0) * 30.4375, 2)
    except (TypeError, ValueError):
        return 0.0


def confidence_label(blockers: list[str], warnings: list[str]) -> str:
    if blockers:
        return "low"
    if warnings:
        return "medium"
    return "high"


def iso_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def order_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def max_present_dates(values: list[Any]) -> date | None:
    parsed = [order_date(value) for value in values]
    present = [value for value in parsed if value is not None]
    return max(present) if present else None
