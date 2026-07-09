from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models.orderpro_order import OrderProOrder, OrderProOrderItem
from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.recommendation import Recommendation
from app.models.usage_history import UsageHistory
from app.services.forecast_input_reconciliation import profile_or_effective_inputs
from app.services.forecasting import build_forecast


STALE_DEMAND_DAYS = 180
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
        "readiness_status": "blocked" if blockers else "ready" if status == "actionable" else "monitor_only",
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
    if last_demand_date and (today - last_demand_date).days > STALE_DEMAND_DAYS and float(forecast.get("total_open_demand") or 0) <= 0:
        warnings.append(f"Stale demand only; last demand is older than {STALE_DEMAND_DAYS} days")
    if demand["negative_or_return_rows"]:
        warnings.append("Demand history includes returns or negative quantities")
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
    if forecast.get("recommended_action") == "reorder" and recommended_qty > 0:
        return "actionable"
    return "monitor"


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


def validate_product_can_create_reorder_recommendation(explanation: dict[str, Any]) -> None:
    if "Missing supplier" in explanation["blockers"]:
        raise ValueError("Product is missing a canonical supplier assignment.")
    if "Missing lead time" in explanation["blockers"]:
        raise ValueError("Product is missing usable supplier lead time.")
    if "No demand history" in explanation["blockers"]:
        raise ValueError("Product is missing demand history or open demand.")
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
