from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.orderpro_order import OrderProOrder, OrderProOrderItem
from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.recommendation import Recommendation
from app.models.stale_demand_review_decision import StaleDemandReviewDecision
from app.models.usage_history import UsageHistory
from app.services.forecast_input_reconciliation import profile_or_effective_inputs
from app.services.forecasting import build_forecast


ACTIONABLE_RECOMMENDATION_STATUSES = {"draft", "pending_review", "accepted"}
ALLOWED_STALE_DEMAND_DECISIONS = {
    "watchlist",
    "manager_approved_one_time",
    "rejected_stale",
    "wait_for_recent_demand",
}
EPSILON = 0.000001
FORMULA_PREFIXES = ("=", "+", "-", "@")


@dataclass(frozen=True)
class RecommendationCsvExport:
    content: bytes
    filename: str
    content_type: str = "text/csv; charset=utf-8"


def stale_demand_recommendations_allowed() -> bool:
    return bool(settings.recommendation_allow_stale_demand or settings.allow_stale_demand_recommendations)


def load_product_for_recommendation_explanation(db: Session, product_id: int) -> Product | None:
    return (
        db.query(Product)
        .options(
            selectinload(Product.supplier_record),
            selectinload(Product.product_suppliers).selectinload(ProductSupplier.supplier),
            selectinload(Product.inventory_positions),
            selectinload(Product.forecast_input_profile),
            selectinload(Product.stale_demand_review_decision),
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
    decision = product.stale_demand_review_decision

    blockers = blockers_for_product(product, effective_inputs, forecast, demand)
    warnings = warnings_for_product(effective_inputs, forecast, demand, today_value)
    status = explanation_status(blockers, forecast, recommended_qty)
    purchase_readiness = purchase_readiness_for_product(
        status=status,
        blockers=blockers,
        warnings=warnings,
        effective_inputs=effective_inputs,
        forecast=forecast,
        recommended_quantity=recommended_qty,
    )
    reasons = reasons_for_product(product, forecast, demand, blockers, status)
    suspicious_issues = suspicious_issues_for_explanation(
        status=status,
        blockers=blockers,
        warnings=warnings,
        forecast=forecast,
        recommended_quantity=recommended_qty,
        minimum_order_quantity=minimum_order_quantity,
        purchase_readiness=purchase_readiness,
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
        "stale_demand_recommendations_allowed": stale_demand_recommendations_allowed(),
        "review_decision": decision.decision if decision else None,
        "reviewed_by": decision.reviewed_by if decision else None,
        "review_notes": decision.notes if decision else None,
        "reviewed_at": decision.reviewed_at.isoformat() if decision else None,
        "decision_status": stale_demand_decision_status(decision),
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
        "pack_size": effective_inputs.get("pack_size"),
        "pack_size_source": effective_inputs.get("pack_size_source"),
        "pack_size_required": settings.recommendation_require_pack_size,
        "raw_required_quantity": forecast.get("raw_required_quantity"),
        "pre_pack_recommended_quantity": forecast.get("pre_pack_recommended_quantity"),
        "order_multiple": forecast.get("order_multiple"),
        "pack_rule_id": forecast.get("pack_rule_id"),
        "pack_rule_name": forecast.get("pack_rule_name"),
        "pack_rule_source": forecast.get("pack_rule_source"),
        "pack_rule_display": forecast.get("pack_rule_display"),
        "pack_rounding_explanation": forecast.get("pack_rounding_explanation"),
        "pack_rule_warnings": forecast.get("pack_rule_warnings") or [],
        "cost_required": settings.recommendation_require_cost,
        "cost_status": "available" if effective_inputs.get("cost_price") is not None else "missing",
        "quantity_satisfies_moq": purchase_readiness["quantity_satisfies_moq"],
        "quantity_satisfies_pack_size": purchase_readiness["quantity_satisfies_pack_size"],
        "quantity_was_raised_to_moq": purchase_readiness["quantity_was_raised_to_moq"],
        "quantity_was_rounded_to_pack_size": purchase_readiness["quantity_was_rounded_to_pack_size"],
        "quantity_review_note": purchase_readiness["quantity_review_note"],
        "purchase_readiness_status": purchase_readiness["status"],
        "purchase_readiness_issues": purchase_readiness["issues"],
        "suggested_cleanup_action": purchase_readiness["suggested_action"],
        "not_ready_for_po": purchase_readiness["not_ready_for_po"],
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
        "purchase_readiness": purchase_readiness,
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
        warnings.append(f"Using fallback MOQ of {effective_inputs.get('min_order_qty')}")
    if "missing_pack_size" in effective_inputs.get("warning_issues", []):
        if settings.recommendation_require_pack_size:
            warnings.append("Missing required pack size")
        else:
            warnings.append("Missing pack size; no order multiple is applied unless reviewed")
    if forecast.get("recommended_action") == "monitor" and float(forecast.get("incoming_qty") or 0) > 0:
        warnings.append("Incoming stock covers the current shortfall")
    if float(forecast.get("recommended_qty") or 0) > 0:
        warnings.extend(quantity_adjustment_warnings(effective_inputs, forecast))
    return warnings


def explanation_status(blockers: list[str], forecast: dict[str, Any], recommended_qty: float) -> str:
    if blockers:
        return "blocked"
    if is_stale_demand_only(forecast) and not stale_demand_recommendations_allowed() and recommended_qty > 0:
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
    if stale_demand_recommendations_allowed():
        return "allowed_by_config_with_warning"
    return "manual_review_required"


def quantity_adjustment_warnings(effective_inputs: dict[str, Any], forecast: dict[str, Any]) -> list[str]:
    warnings = []
    info = quantity_quality_info(effective_inputs, forecast, float(forecast.get("recommended_qty") or 0))
    if info["quantity_was_raised_to_moq"]:
        warnings.append(
            f"Recommended quantity was raised to MOQ {info['minimum_order_quantity']} from raw need {info['raw_recommended_quantity']}"
        )
    if info["quantity_was_rounded_to_pack_size"]:
        warnings.append(
            f"Recommended quantity was rounded to pack size {info['pack_size']} from {info['pre_pack_quantity']}"
        )
    return warnings


def quantity_quality_info(
    effective_inputs: dict[str, Any],
    forecast: dict[str, Any],
    recommended_quantity: float,
) -> dict[str, Any]:
    minimum_order_quantity = parse_positive(effective_inputs.get("min_order_qty"))
    pack_context = forecast.get("pack_rule_context") or {}
    pack_size = parse_positive(pack_context.get("order_multiple")) or parse_positive(effective_inputs.get("pack_size"))
    raw_quantity = max(
        float(pack_context.get("raw_required_quantity") if pack_context else forecast.get("raw_required_quantity") or 0),
        0.0,
    )
    pre_pack_quantity = float(pack_context.get("pre_pack_quantity") or 0) if pack_context else (
        round(max(raw_quantity, minimum_order_quantity or 0), 6) if raw_quantity > 0 else 0.0
    )
    quantity_satisfies_moq = (
        minimum_order_quantity is None
        or recommended_quantity <= 0
        or recommended_quantity + EPSILON >= minimum_order_quantity
    )
    quantity_satisfies_pack_size = (
        pack_size is None
        or recommended_quantity <= 0
        or is_multiple(recommended_quantity, pack_size)
    )
    quantity_was_raised_to_moq = (
        recommended_quantity > 0
        and minimum_order_quantity is not None
        and raw_quantity > 0
        and raw_quantity + EPSILON < minimum_order_quantity
        and recommended_quantity + EPSILON >= minimum_order_quantity
    )
    quantity_was_rounded_to_pack_size = (
        recommended_quantity > 0
        and pack_size is not None
        and pre_pack_quantity > 0
        and recommended_quantity > pre_pack_quantity + EPSILON
        and is_multiple(recommended_quantity, pack_size)
    )
    return {
        "minimum_order_quantity": minimum_order_quantity,
        "moq_source": effective_inputs.get("moq_source"),
        "pack_size": pack_size,
        "pack_size_source": pack_context.get("rule_source") or effective_inputs.get("pack_size_source"),
        "pack_rule_name": pack_context.get("rule_name"),
        "pack_rule_display": pack_context.get("display"),
        "pack_rounding_explanation": pack_context.get("explanation"),
        "raw_recommended_quantity": round(raw_quantity, 6),
        "pre_pack_quantity": pre_pack_quantity,
        "quantity_satisfies_moq": quantity_satisfies_moq,
        "quantity_satisfies_pack_size": quantity_satisfies_pack_size,
        "quantity_was_raised_to_moq": quantity_was_raised_to_moq,
        "quantity_was_rounded_to_pack_size": quantity_was_rounded_to_pack_size,
    }


def purchase_readiness_for_product(
    *,
    status: str,
    blockers: list[str],
    warnings: list[str],
    effective_inputs: dict[str, Any],
    forecast: dict[str, Any],
    recommended_quantity: float,
) -> dict[str, Any]:
    quality = quantity_quality_info(effective_inputs, forecast, recommended_quantity)
    hard_issues = []
    review_issues = []
    if blockers:
        hard_issues.extend(blockers)
    if forecast.get("recommended_action") != "reorder":
        hard_issues.append("Forecast action is not reorder")
    if recommended_quantity <= 0:
        hard_issues.append("Non-positive recommendation quantity")
    if is_stale_demand_only(forecast) and not stale_demand_recommendations_allowed():
        hard_issues.append("Stale-only demand requires manual review")
    if not quality["quantity_satisfies_moq"]:
        review_issues.append("Recommended quantity is below MOQ")
    if not quality["quantity_satisfies_pack_size"]:
        review_issues.append("Recommended quantity is not a pack-size multiple")
    if effective_inputs.get("pack_size") is None and recommended_quantity > 0 and settings.recommendation_require_pack_size:
        hard_issues.append("Missing pack size")
    if "missing_cost" in effective_inputs.get("warning_issues", []):
        if settings.recommendation_require_cost:
            hard_issues.append("Missing cost")
        else:
            review_issues.append("Missing cost")
    if "fallback_moq" in effective_inputs.get("warning_issues", []):
        review_issues.append("Using fallback MOQ")
    if any("return" in warning.lower() or "negative" in warning.lower() for warning in warnings):
        review_issues.append("Returns or negative demand need review")
    if quality["quantity_was_raised_to_moq"]:
        review_issues.append("Quantity was raised to MOQ")
    if quality["quantity_was_rounded_to_pack_size"]:
        review_issues.append("Quantity was rounded to pack size")

    if hard_issues:
        readiness_status = "blocked"
    elif review_issues:
        readiness_status = "needs_review"
    else:
        readiness_status = "order_ready"

    unique_issues = unique_preserve_order(hard_issues + review_issues)
    return {
        "status": readiness_status,
        "issues": unique_issues,
        "suggested_action": suggested_cleanup_action(unique_issues, readiness_status),
        "not_ready_for_po": readiness_status != "order_ready",
        "quantity_review_note": quantity_review_note(readiness_status, unique_issues, quality),
        **quality,
    }


def suggested_cleanup_action(issues: list[str], readiness_status: str) -> str:
    if readiness_status == "order_ready":
        return "none"
    issue_text = " ".join(issues).lower()
    if "missing supplier" in issue_text or "missing lead time" in issue_text:
        return "update_after_supplier_fix"
    if "missing pack size" in issue_text or "pack-size" in issue_text or "pack size" in issue_text:
        return "update_after_pack_size_fix" if settings.recommendation_require_pack_size else "review_pack_size_optional"
    if "stale-only" in issue_text:
        return "review_stale_demand"
    if "forecast action is not reorder" in issue_text:
        return "convert_to_watchlist"
    if "missing cost" in issue_text:
        return "review_missing_cost"
    if "moq" in issue_text:
        return "review"
    return "reject_existing_recommendation" if readiness_status == "blocked" else "review"


def quantity_review_note(readiness_status: str, issues: list[str], quality: dict[str, Any]) -> str:
    if readiness_status == "order_ready":
        return "Ready for PO using current MOQ and pack-size inputs."
    if "Missing pack size" in issues:
        if settings.recommendation_require_pack_size:
            return "Not ready for PO: pack size is required by the current recommendation policy."
        return "Review before PO: pack size is optional and missing, so no pack multiple was applied."
    if "Recommended quantity is not a pack-size multiple" in issues:
        return "Not ready for PO: recommended quantity is not a pack-size multiple."
    if "Quantity was rounded to pack size" in issues:
        return f"Review before PO: quantity was rounded to pack size {quality['pack_size']}."
    if "Quantity was raised to MOQ" in issues:
        return f"Review before PO: quantity was raised to MOQ {quality['minimum_order_quantity']}."
    if "Stale-only demand requires manual review" in issues:
        return "Not ready for PO: demand is stale-only and should be reviewed."
    return "Not ready for PO: review blockers and warnings first."


def parse_positive(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def is_multiple(quantity: float, multiple: float) -> bool:
    if multiple <= 0:
        return False
    ratio = quantity / multiple
    return abs(ratio - round(ratio)) < EPSILON


def unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    unique = []
    for value in values:
        if value not in seen:
            unique.append(value)
            seen.add(value)
    return unique


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
    purchase_readiness: dict[str, Any] | None = None,
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
    if is_actionable and purchase_readiness and purchase_readiness.get("status") != "order_ready":
        issues.append(f"Actionable recommendation is not purchase-ready: {purchase_readiness.get('status')}")
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
            purchase_readiness=explanation["purchase_readiness"],
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
                "purchase_readiness_status": explanation["purchase_readiness_status"],
                "purchase_readiness_issues": explanation["purchase_readiness_issues"],
                "suggested_cleanup_action": explanation["suggested_cleanup_action"],
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


def cleanup_candidates(db: Session, *, limit: int = 500) -> dict[str, Any]:
    recommendations = (
        db.query(Recommendation)
        .options(
            selectinload(Recommendation.product).selectinload(Product.supplier_record),
            selectinload(Recommendation.supplier),
        )
        .order_by(Recommendation.id.asc())
        .limit(limit)
        .all()
    )
    issue_counter: Counter[str] = Counter()
    action_counter: Counter[str] = Counter()
    candidates = []

    for recommendation in recommendations:
        explanation = explain_product_recommendation(db, recommendation.product_id)
        if explanation is None:
            issues = ["Product missing"]
            action = "reject_existing_recommendation"
            readiness_status = "blocked"
            product_name = None
            supplier_name = recommendation.supplier.name if recommendation.supplier else None
        else:
            issues = cleanup_issues_for_recommendation(recommendation, explanation)
            action = cleanup_action_for_recommendation(issues, explanation)
            readiness_status = explanation["purchase_readiness_status"]
            product_name = explanation["product_name"]
            supplier_name = explanation["supplier_name"]

        if not issues:
            continue

        issue_counter.update(issues)
        action_counter[action] += 1
        candidates.append(
            {
                "recommendation_id": recommendation.id,
                "product_id": recommendation.product_id,
                "product_name": product_name,
                "supplier_id": recommendation.supplier_id,
                "supplier_name": supplier_name,
                "status": recommendation.status,
                "recommended_quantity": recommendation.recommended_qty,
                "raw_required_quantity": explanation.get("raw_required_quantity") if explanation else None,
                "final_recommended_quantity": explanation.get("recommended_quantity") if explanation else recommendation.recommended_qty,
                "order_multiple": explanation.get("order_multiple") if explanation else None,
                "pack_rule_name": explanation.get("pack_rule_name") if explanation else None,
                "pack_rule_source": explanation.get("pack_rule_source") if explanation else None,
                "pack_rule_display": explanation.get("pack_rule_display") if explanation else None,
                "pack_rounding_explanation": explanation.get("pack_rounding_explanation") if explanation else None,
                "purchase_readiness_status": readiness_status,
                "issues": issues,
                "suggested_action": action,
                "blockers": explanation.get("blockers") if explanation else [],
                "warnings": explanation.get("warnings") if explanation else [],
            }
        )

    return {
        "summary": {
            "recommendations_evaluated": len(recommendations),
            "total_candidates": len(candidates),
            "issue_counts": dict(issue_counter),
            "suggested_action_counts": dict(action_counter),
            "limit": limit,
        },
        "candidates": candidates,
    }


def recommendation_review_summary(db: Session, *, limit: int = 500) -> dict[str, Any]:
    status_rows = db.query(Recommendation.status, func.count(Recommendation.id)).group_by(Recommendation.status).all()
    recommendation_status_counts = {status or "unknown": int(count) for status, count in status_rows}
    total_recommendations = sum(recommendation_status_counts.values())
    stale_review = stale_demand_review_candidates(db, limit=limit, decision_filter="all")
    decisions = list_stale_demand_review_decisions(db, limit=limit)
    manager_queue = manager_approved_stale_queue(db, limit=limit)
    cleanup = cleanup_candidates(db, limit=limit)
    queue_status_counts = manager_queue["summary"]["safety_status_counts"]
    cleanup_issue_counts = cleanup["summary"]["issue_counts"]
    return {
        "summary": {
            "total_existing_recommendations": total_recommendations,
            "pending_review_recommendations": recommendation_status_counts.get("pending_review", 0),
            "accepted_recommendations": recommendation_status_counts.get("accepted", 0),
            "rejected_recommendations": recommendation_status_counts.get("rejected", 0),
            "recommendation_status_counts": recommendation_status_counts,
            "stale_demand_candidates": stale_review["summary"]["total_candidates"],
            "stale_demand_decisions_by_type": decisions["summary"]["decision_counts"],
            "manager_approved_stale_queue_count": manager_queue["summary"]["total_candidates"],
            "manager_approved_stale_queue_by_safety_status": queue_status_counts,
            "cleanup_candidates_count": cleanup["summary"]["total_candidates"],
            "cleanup_candidates_by_issue": cleanup_issue_counts,
            "recommendations_ready_for_manual_review": queue_status_counts.get("ready_for_manual_recommendation", 0),
            "recommendations_blocked_from_po_conversion": cleanup["summary"]["total_candidates"]
            + queue_status_counts.get("blocked", 0),
            "limit": limit,
        }
    }


def build_recommendation_review_summary_csv(db: Session, *, limit: int = 500) -> RecommendationCsvExport:
    summary = recommendation_review_summary(db, limit=limit)["summary"]
    rows: list[dict[str, Any]] = []
    for key, value in summary.items():
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                rows.append({"Metric": f"{key}.{nested_key}", "Value": nested_value})
        else:
            rows.append({"Metric": key, "Value": value})
    return build_csv_export(
        ["Metric", "Value"],
        rows,
        f"recommendation_review_summary_{datetime.now(timezone.utc).date().isoformat()}.csv",
    )


def build_stale_demand_review_csv(
    db: Session,
    *,
    limit: int = 500,
    decision_filter: str = "all",
) -> RecommendationCsvExport:
    report = stale_demand_review_candidates(db, limit=limit, decision_filter=decision_filter)
    rows = [
        {
            "Product ID": item.get("product_id"),
            "Product Name": item.get("product_name"),
            "Supplier": item.get("supplier_name"),
            "Last Demand Date": item.get("last_demand_date"),
            "Days Since Last Demand": item.get("days_since_last_demand"),
            "Demand Rows": item.get("demand_rows"),
            "Monthly Average Demand": item.get("monthly_average_demand"),
            "Current Stock": item.get("current_stock"),
            "Lead Time": item.get("lead_time_days"),
            "Advisory Quantity": item.get("advisory_recommended_quantity"),
            "Raw Quantity": item.get("raw_required_quantity"),
            "Final Recommended Quantity": item.get("final_recommended_quantity"),
            "Order Multiple": item.get("order_multiple"),
            "Pack Rule": item.get("pack_rule_name"),
            "Pack Rule Source": item.get("pack_rule_source"),
            "Pack Explanation": item.get("pack_rounding_explanation"),
            "Estimated Cost": item.get("estimated_total_cost"),
            "Suggested Action": item.get("suggested_action"),
            "Review Decision": item.get("review_decision"),
            "Reviewed By": item.get("reviewed_by"),
            "Review Notes": item.get("review_notes"),
        }
        for item in report["items"]
    ]
    return build_csv_export(
        [
            "Product ID",
            "Product Name",
            "Supplier",
            "Last Demand Date",
            "Days Since Last Demand",
            "Demand Rows",
            "Monthly Average Demand",
            "Current Stock",
            "Lead Time",
            "Advisory Quantity",
            "Raw Quantity",
            "Final Recommended Quantity",
            "Order Multiple",
            "Pack Rule",
            "Pack Rule Source",
            "Pack Explanation",
            "Estimated Cost",
            "Suggested Action",
            "Review Decision",
            "Reviewed By",
            "Review Notes",
        ],
        rows,
        f"stale_demand_review_{datetime.now(timezone.utc).date().isoformat()}.csv",
    )


def build_manager_approved_stale_queue_csv(db: Session, *, limit: int = 500) -> RecommendationCsvExport:
    report = manager_approved_stale_queue(db, limit=limit)
    rows = [
        {
            "Product ID": item.get("product_id"),
            "Product Name": item.get("product_name"),
            "Supplier": item.get("supplier_name"),
            "Lead Time": item.get("lead_time_days"),
            "Current Stock": item.get("current_stock"),
            "Last Demand Date": item.get("last_demand_date"),
            "Advisory Quantity": item.get("advisory_recommended_quantity"),
            "Raw Quantity": item.get("raw_required_quantity"),
            "Final Recommended Quantity": item.get("final_recommended_quantity"),
            "Order Multiple": item.get("order_multiple"),
            "Pack Rule": item.get("pack_rule_name"),
            "Pack Rule Source": item.get("pack_rule_source"),
            "Pack Explanation": item.get("pack_rounding_explanation"),
            "Estimated Unit Cost": item.get("estimated_unit_cost"),
            "Estimated Total Cost": item.get("estimated_total_cost"),
            "Reviewed By": item.get("reviewed_by"),
            "Reviewed At": item.get("reviewed_at"),
            "Review Notes": item.get("review_notes"),
            "Safety Status": item.get("safety_status"),
            "Safety Blockers": join_csv_list(item.get("safety_blockers")),
            "Warnings": join_csv_list(item.get("warnings")),
            "Suggested Next Action": item.get("suggested_next_action"),
        }
        for item in report["items"]
    ]
    return build_csv_export(
        [
            "Product ID",
            "Product Name",
            "Supplier",
            "Lead Time",
            "Current Stock",
            "Last Demand Date",
            "Advisory Quantity",
            "Raw Quantity",
            "Final Recommended Quantity",
            "Order Multiple",
            "Pack Rule",
            "Pack Rule Source",
            "Pack Explanation",
            "Estimated Unit Cost",
            "Estimated Total Cost",
            "Reviewed By",
            "Reviewed At",
            "Review Notes",
            "Safety Status",
            "Safety Blockers",
            "Warnings",
            "Suggested Next Action",
        ],
        rows,
        f"manager_approved_stale_queue_{datetime.now(timezone.utc).date().isoformat()}.csv",
    )


def build_cleanup_candidates_csv(db: Session, *, limit: int = 500) -> RecommendationCsvExport:
    report = cleanup_candidates(db, limit=limit)
    rows = [
        {
            "Recommendation ID": item.get("recommendation_id"),
            "Product ID": item.get("product_id"),
            "Product Name": item.get("product_name"),
            "Supplier": item.get("supplier_name"),
            "Status": item.get("status"),
            "Quantity": item.get("recommended_quantity"),
            "Raw Quantity": item.get("raw_required_quantity"),
            "Final Recommended Quantity": item.get("final_recommended_quantity"),
            "Order Multiple": item.get("order_multiple"),
            "Pack Rule": item.get("pack_rule_name"),
            "Pack Rule Source": item.get("pack_rule_source"),
            "Pack Explanation": item.get("pack_rounding_explanation"),
            "Issues": join_csv_list(item.get("issues")),
            "Suggested Action": item.get("suggested_action"),
            "Purchase Readiness": item.get("purchase_readiness_status"),
            "Blockers": join_csv_list(item.get("blockers")),
            "Warnings": join_csv_list(item.get("warnings")),
        }
        for item in report["candidates"]
    ]
    return build_csv_export(
        [
            "Recommendation ID",
            "Product ID",
            "Product Name",
            "Supplier",
            "Status",
            "Quantity",
            "Raw Quantity",
            "Final Recommended Quantity",
            "Order Multiple",
            "Pack Rule",
            "Pack Rule Source",
            "Pack Explanation",
            "Issues",
            "Suggested Action",
            "Purchase Readiness",
            "Blockers",
            "Warnings",
        ],
        rows,
        f"recommendation_cleanup_candidates_{datetime.now(timezone.utc).date().isoformat()}.csv",
    )


def stale_demand_review_candidates(
    db: Session,
    *,
    limit: int = 500,
    decision_filter: str = "unreviewed",
    today: date | None = None,
) -> dict[str, Any]:
    normalized_filter = normalize_stale_demand_decision_filter(decision_filter)
    today_value = today or datetime.now(timezone.utc).date()
    products = (
        db.query(Product)
        .options(
            selectinload(Product.supplier_record),
            selectinload(Product.product_suppliers).selectinload(ProductSupplier.supplier),
            selectinload(Product.inventory_positions),
            selectinload(Product.forecast_input_profile),
            selectinload(Product.stale_demand_review_decision),
        )
        .order_by(Product.id.asc())
        .limit(limit)
        .all()
    )
    items = []
    skipped_counter: Counter[str] = Counter()
    action_counter: Counter[str] = Counter()

    for product in products:
        explanation = explain_product_recommendation(db, product.id, today=today_value)
        if explanation is None:
            skipped_counter["missing_explanation"] += 1
            continue
        include, reason = is_stale_demand_review_candidate(explanation)
        if not include:
            skipped_counter[reason] += 1
            continue
        decision = explanation.get("review_decision")
        if not stale_demand_decision_matches_filter(decision, normalized_filter):
            skipped_counter["decision_filter_excluded"] += 1
            continue

        action = stale_demand_review_suggested_action(explanation)
        action_counter[action] += 1
        last_demand = parse_iso_date(explanation.get("last_demand_date"))
        days_since_last_demand = (today_value - last_demand).days if last_demand else None
        estimated_unit_cost = effective_unit_cost_from_explanation(explanation)
        recommended_quantity = float(explanation.get("recommended_quantity") or 0)
        estimated_total_cost = (
            round(recommended_quantity * estimated_unit_cost, 2)
            if estimated_unit_cost is not None
            else None
        )
        items.append(
            {
                "product_id": explanation["product_id"],
                "product_name": explanation["product_name"],
                "orderpro_sku": explanation.get("orderpro_sku"),
                "supplier_id": explanation.get("supplier_id"),
                "supplier_name": explanation.get("supplier_name"),
                "last_demand_date": explanation.get("last_demand_date"),
                "days_since_last_demand": days_since_last_demand,
                "demand_rows": explanation.get("demand_rows"),
                "monthly_average_demand": explanation.get("monthly_average_demand"),
                "current_stock": explanation.get("current_stock"),
                "lead_time_days": explanation.get("lead_time_days"),
                "advisory_recommended_quantity": recommended_quantity,
                "raw_required_quantity": explanation.get("raw_required_quantity"),
                "final_recommended_quantity": explanation.get("recommended_quantity"),
                "order_multiple": explanation.get("order_multiple"),
                "pack_rule_name": explanation.get("pack_rule_name"),
                "pack_rule_source": explanation.get("pack_rule_source"),
                "pack_rule_display": explanation.get("pack_rule_display"),
                "pack_rounding_explanation": explanation.get("pack_rounding_explanation"),
                "estimated_unit_cost": estimated_unit_cost,
                "estimated_total_cost": estimated_total_cost,
                "blockers": explanation.get("blockers") or [],
                "warnings": explanation.get("warnings") or [],
                "purchase_readiness_issues": explanation.get("purchase_readiness_issues") or [],
                "suggested_action": action,
                "stale_demand_policy": explanation.get("stale_demand_policy"),
                "review_decision": explanation.get("review_decision"),
                "reviewed_by": explanation.get("reviewed_by"),
                "review_notes": explanation.get("review_notes"),
                "reviewed_at": explanation.get("reviewed_at"),
                "decision_status": explanation.get("decision_status"),
                "recommendation_status": explanation.get("status"),
                "purchase_readiness_status": explanation.get("purchase_readiness_status"),
            }
        )

    items.sort(
        key=lambda item: (
            -(item["advisory_recommended_quantity"] or 0),
            item["days_since_last_demand"] if item["days_since_last_demand"] is not None else -1,
            item["product_id"],
        )
    )
    return {
        "summary": {
            "products_evaluated": len(products),
            "total_candidates": len(items),
            "suggested_action_counts": dict(action_counter),
            "skipped_counts": dict(skipped_counter),
            "limit": limit,
            "decision_filter": normalized_filter,
        },
        "items": items,
    }


def manager_approved_stale_queue(
    db: Session,
    *,
    limit: int = 500,
    today: date | None = None,
) -> dict[str, Any]:
    today_value = today or datetime.now(timezone.utc).date()
    decisions = (
        db.query(StaleDemandReviewDecision)
        .options(selectinload(StaleDemandReviewDecision.product))
        .filter(StaleDemandReviewDecision.decision == "manager_approved_one_time")
        .order_by(StaleDemandReviewDecision.reviewed_at.desc(), StaleDemandReviewDecision.id.desc())
        .limit(limit)
        .all()
    )
    items = []
    status_counter: Counter[str] = Counter()
    action_counter: Counter[str] = Counter()
    for decision in decisions:
        item = manager_approved_stale_queue_item(db, decision, today=today_value)
        items.append(item)
        status_counter[item["safety_status"]] += 1
        action_counter[item["suggested_next_action"]] += 1

    return {
        "summary": {
            "decisions_evaluated": len(decisions),
            "total_candidates": len(items),
            "safety_status_counts": dict(status_counter),
            "suggested_next_action_counts": dict(action_counter),
            "limit": limit,
        },
        "items": items,
    }


def manager_approved_stale_queue_item(
    db: Session,
    decision: StaleDemandReviewDecision,
    *,
    today: date,
) -> dict[str, Any]:
    explanation = explain_product_recommendation(db, decision.product_id, today=today)
    if explanation is None:
        return {
            "product_id": decision.product_id,
            "product_name": None,
            "orderpro_sku": None,
            "supplier_id": None,
            "supplier_name": None,
            "lead_time_days": None,
            "current_stock": None,
            "last_demand_date": None,
            "days_since_last_demand": None,
            "advisory_recommended_quantity": 0.0,
            "raw_required_quantity": None,
            "final_recommended_quantity": 0.0,
            "order_multiple": None,
            "pack_rule_name": None,
            "pack_rule_source": None,
            "pack_rule_display": None,
            "pack_rounding_explanation": None,
            "estimated_unit_cost": None,
            "estimated_total_cost": None,
            "reviewed_by": decision.reviewed_by,
            "review_notes": decision.notes,
            "reviewed_at": decision.reviewed_at.isoformat() if decision.reviewed_at else None,
            "review_decision": decision.decision,
            "safety_status": "blocked",
            "safety_blockers": ["Product no longer exists"],
            "warnings": [],
            "suggested_next_action": "resolve_hard_blockers",
            "recommendation_status": None,
            "purchase_readiness_status": None,
        }

    last_demand = parse_iso_date(explanation.get("last_demand_date"))
    days_since_last_demand = (today - last_demand).days if last_demand else None
    recommended_quantity = float(explanation.get("recommended_quantity") or 0)
    estimated_unit_cost = effective_unit_cost_from_explanation(explanation)
    estimated_total_cost = (
        round(recommended_quantity * estimated_unit_cost, 2)
        if estimated_unit_cost is not None
        else None
    )
    safety = manager_approved_stale_safety(explanation)
    return {
        "product_id": explanation["product_id"],
        "product_name": explanation["product_name"],
        "orderpro_sku": explanation.get("orderpro_sku"),
        "supplier_id": explanation.get("supplier_id"),
        "supplier_name": explanation.get("supplier_name"),
        "lead_time_days": explanation.get("lead_time_days"),
        "current_stock": explanation.get("current_stock"),
        "last_demand_date": explanation.get("last_demand_date"),
        "days_since_last_demand": days_since_last_demand,
        "advisory_recommended_quantity": recommended_quantity,
        "raw_required_quantity": explanation.get("raw_required_quantity"),
        "final_recommended_quantity": explanation.get("recommended_quantity"),
        "order_multiple": explanation.get("order_multiple"),
        "pack_rule_name": explanation.get("pack_rule_name"),
        "pack_rule_source": explanation.get("pack_rule_source"),
        "pack_rule_display": explanation.get("pack_rule_display"),
        "pack_rounding_explanation": explanation.get("pack_rounding_explanation"),
        "estimated_unit_cost": estimated_unit_cost,
        "estimated_total_cost": estimated_total_cost,
        "reviewed_by": decision.reviewed_by,
        "review_notes": decision.notes,
        "reviewed_at": decision.reviewed_at.isoformat() if decision.reviewed_at else None,
        "review_decision": decision.decision,
        "safety_status": safety["safety_status"],
        "safety_blockers": safety["safety_blockers"],
        "warnings": safety["warnings"],
        "suggested_next_action": safety["suggested_next_action"],
        "recommendation_status": explanation.get("status"),
        "purchase_readiness_status": explanation.get("purchase_readiness_status"),
    }


def manager_approved_stale_safety(explanation: dict[str, Any]) -> dict[str, Any]:
    blockers = []
    warnings = [
        warning
        for warning in (explanation.get("warnings") or [])
        if not str(warning).startswith("Stale demand only")
    ]
    if explanation.get("review_decision") != "manager_approved_one_time":
        blockers.append("Latest stale-demand decision is not manager-approved one-time")
    if "Product is non-inventory" in set(explanation.get("blockers") or []):
        blockers.append("Product is non-inventory")
    if "Missing supplier" in set(explanation.get("blockers") or []) or explanation.get("supplier_id") is None:
        blockers.append("Missing supplier")
    if "Missing lead time" in set(explanation.get("blockers") or []):
        blockers.append("Missing lead time")
    if "No demand history" in set(explanation.get("blockers") or []):
        blockers.append("No demand history")
    if float(explanation.get("recommended_quantity") or 0) <= 0:
        blockers.append("Non-positive recommendation quantity")
    if explanation.get("recommended_action") != "reorder":
        blockers.append("Forecast action is not reorder")
    if not explanation.get("stale_demand_only"):
        blockers.append("Product is not currently stale-demand-only")

    purchase_issues = list(explanation.get("purchase_readiness_issues") or [])
    advisory_issues = [
        issue
        for issue in purchase_issues
        if issue not in set(blockers) and issue != "Stale-only demand requires manual review"
    ]
    for issue in advisory_issues:
        if issue not in warnings:
            warnings.append(issue)

    if blockers:
        status = "blocked"
        action = "resolve_hard_blockers"
    elif warnings:
        status = "needs_review"
        action = "review_warnings_before_recommendation"
    else:
        status = "ready_for_manual_recommendation"
        action = "create_review_recommendation"
    return {
        "safety_status": status,
        "safety_blockers": unique_preserve_order(blockers),
        "warnings": unique_preserve_order(warnings),
        "suggested_next_action": action,
    }


def validate_manager_approved_stale_queue_item(explanation: dict[str, Any]) -> None:
    safety = manager_approved_stale_safety(explanation)
    if safety["safety_status"] != "ready_for_manual_recommendation":
        reasons = safety["safety_blockers"] or safety["warnings"]
        detail = "; ".join(reasons) if reasons else "Product is not ready for manual stale-demand recommendation."
        raise ValueError(detail)


def normalize_stale_demand_decision_filter(value: str | None) -> str:
    normalized = (value or "unreviewed").strip().lower()
    allowed = ALLOWED_STALE_DEMAND_DECISIONS | {"unreviewed", "all"}
    if normalized not in allowed:
        raise ValueError("Invalid stale-demand decision filter.")
    return normalized


def stale_demand_decision_matches_filter(decision: str | None, decision_filter: str) -> bool:
    if decision_filter == "all":
        return True
    if decision_filter == "unreviewed":
        return decision is None
    return decision == decision_filter


def stale_demand_decision_status(decision: StaleDemandReviewDecision | None) -> str:
    return decision.decision if decision else "unreviewed"


def is_stale_demand_review_candidate(explanation: dict[str, Any]) -> tuple[bool, str]:
    if not explanation.get("stale_demand_only"):
        return False, "not_stale_only"
    blockers = set(explanation.get("blockers") or [])
    real_blockers = blockers - {"Stale-only demand requires manual review"}
    if real_blockers:
        return False, "has_hard_blocker"
    if "Stale-only demand requires manual review" not in set(explanation.get("purchase_readiness_issues") or []):
        return False, "not_blocked_by_stale_demand"
    if explanation.get("supplier_id") is None:
        return False, "missing_supplier"
    if explanation.get("lead_time_days") is None or float(explanation.get("lead_time_days") or 0) <= 0:
        return False, "missing_lead_time"
    if float(explanation.get("recommended_quantity") or 0) <= 0:
        return False, "non_positive_quantity"
    if explanation.get("recommended_action") != "reorder":
        return False, "not_reorder"
    if explanation.get("purchase_readiness_status") == "order_ready":
        return False, "already_order_ready"
    return True, "candidate"


def list_stale_demand_review_decisions(db: Session, *, limit: int = 500) -> dict[str, Any]:
    decisions = (
        db.query(StaleDemandReviewDecision)
        .options(selectinload(StaleDemandReviewDecision.product))
        .order_by(StaleDemandReviewDecision.updated_at.desc(), StaleDemandReviewDecision.id.desc())
        .limit(limit)
        .all()
    )
    counter = Counter(decision.decision for decision in decisions)
    return {
        "summary": {
            "total_decisions": len(decisions),
            "decision_counts": dict(counter),
            "limit": limit,
        },
        "items": [serialize_stale_demand_review_decision(decision) for decision in decisions],
    }


def save_stale_demand_review_decision(
    db: Session,
    product_id: int,
    *,
    decision: str,
    reviewed_by: str,
    notes: str | None = None,
) -> StaleDemandReviewDecision:
    normalized_decision = normalize_stale_demand_decision(decision)
    reviewer = (reviewed_by or "").strip()
    if not reviewer:
        raise ValueError("reviewed_by is required.")

    product = load_product_for_recommendation_explanation(db, product_id)
    if product is None:
        raise LookupError("Product not found.")

    explanation = explain_product_recommendation(db, product_id)
    if explanation is None:
        raise LookupError("Product not found.")
    eligible, _reason = is_stale_demand_review_candidate(explanation)
    if normalized_decision not in {"watchlist", "rejected_stale"} and not eligible:
        raise ValueError("Product is not currently eligible for this stale-demand decision.")

    now = datetime.utcnow()
    review = (
        db.query(StaleDemandReviewDecision)
        .filter(StaleDemandReviewDecision.product_id == product_id)
        .one_or_none()
    )
    if review is None:
        review = StaleDemandReviewDecision(product_id=product_id, created_at=now)
        db.add(review)
    review.decision = normalized_decision
    review.reviewed_by = reviewer
    review.notes = notes
    review.reviewed_at = now
    review.updated_at = now
    db.commit()
    db.refresh(review)
    return review


def normalize_stale_demand_decision(decision: str) -> str:
    normalized = (decision or "").strip().lower()
    if normalized not in ALLOWED_STALE_DEMAND_DECISIONS:
        raise ValueError("Invalid stale-demand review decision.")
    return normalized


def serialize_stale_demand_review_decision(decision: StaleDemandReviewDecision) -> dict[str, Any]:
    product = decision.product
    return {
        "id": decision.id,
        "product_id": decision.product_id,
        "product_name": product.name if product else None,
        "orderpro_sku": product.orderpro_sku if product else None,
        "recommendation_id": decision.recommendation_id,
        "decision": decision.decision,
        "reviewed_by": decision.reviewed_by,
        "notes": decision.notes,
        "reviewed_at": decision.reviewed_at.isoformat() if decision.reviewed_at else None,
        "created_at": decision.created_at.isoformat() if decision.created_at else None,
        "updated_at": decision.updated_at.isoformat() if decision.updated_at else None,
    }


def stale_demand_review_suggested_action(explanation: dict[str, Any]) -> str:
    warnings = " ".join(explanation.get("warnings") or []).lower()
    if "return" in warnings or "negative" in warnings:
        return "manual_review"
    current_stock = float(explanation.get("current_stock") or 0)
    recommended_quantity = float(explanation.get("recommended_quantity") or 0)
    if current_stock <= 0 and recommended_quantity > 0:
        return "approve_one_time_reorder"
    return "manual_review"


def effective_unit_cost_from_explanation(explanation: dict[str, Any]) -> float | None:
    snapshot = explanation.get("forecast_snapshot") or {}
    for value in (
        snapshot.get("cost_price"),
        snapshot.get("estimated_unit_cost"),
        snapshot.get("unit_cost"),
    ):
        parsed = parse_positive(value)
        if parsed is not None:
            return parsed
    return None


def build_csv_export(
    columns: list[str],
    rows: list[dict[str, Any]],
    filename: str,
) -> RecommendationCsvExport:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: csv_safe_value(row.get(column)) for column in columns})
    return RecommendationCsvExport(content=("\ufeff" + handle.getvalue()).encode("utf-8"), filename=filename)


def csv_safe_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    if text.startswith(FORMULA_PREFIXES):
        return f"'{text}"
    return text


def join_csv_list(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def cleanup_issues_for_recommendation(recommendation: Recommendation, explanation: dict[str, Any]) -> list[str]:
    issues = []
    actionable_existing = recommendation.status in ACTIONABLE_RECOMMENDATION_STATUSES
    if actionable_existing and explanation.get("stale_demand_only"):
        issues.append("stale_demand_review_required")
    if "Missing supplier" in explanation["blockers"]:
        issues.append("missing supplier")
    if "Missing lead time" in explanation["blockers"]:
        issues.append("missing lead time")
    if "No demand history" in explanation["blockers"]:
        issues.append("no demand")
    if float(recommendation.recommended_qty or 0) <= 0:
        issues.append("non-positive quantity")
    minimum_order_quantity = parse_positive(explanation.get("minimum_order_quantity"))
    if minimum_order_quantity and 0 < float(recommendation.recommended_qty or 0) < minimum_order_quantity:
        issues.append("quantity below MOQ")
    if (
        settings.recommendation_require_pack_size
        and explanation.get("pack_size") is None
        and float(recommendation.recommended_qty or 0) > 0
    ):
        issues.append("missing pack size")
    if "Missing cost" in explanation["warnings"]:
        issues.append("cost missing")
    if explanation.get("recommended_action") != "reorder":
        issues.append("enough stock/no reorder needed")
    if explanation.get("purchase_readiness_status") != "order_ready":
        for issue in explanation.get("purchase_readiness_issues", []):
            cleanup_issue = cleanup_issue_name(issue)
            if cleanup_issue == "stale_demand_review_required" and not actionable_existing:
                cleanup_issue = "stale-only demand review"
            issues.append(cleanup_issue)
    return unique_preserve_order(issues)


def cleanup_issue_name(issue: str) -> str:
    issue_lower = issue.lower()
    if "missing supplier" in issue_lower:
        return "missing supplier"
    if "missing lead time" in issue_lower:
        return "missing lead time"
    if "no demand" in issue_lower:
        return "no demand"
    if "non-positive" in issue_lower:
        return "non-positive quantity"
    if "below moq" in issue_lower:
        return "quantity below MOQ"
    if "missing pack size" in issue_lower:
        return "missing pack size"
    if "missing cost" in issue_lower:
        return "cost missing"
    if "forecast action is not reorder" in issue_lower:
        return "enough stock/no reorder needed"
    if "stale-only" in issue_lower:
        return "stale_demand_review_required"
    if "raised to moq" in issue_lower:
        return "quantity raised to MOQ"
    if "rounded to pack size" in issue_lower or "pack-size multiple" in issue_lower:
        return "quantity needs pack-size review"
    if "fallback moq" in issue_lower:
        return "fallback MOQ"
    if "returns" in issue_lower or "negative" in issue_lower:
        return "returns/negative demand review"
    return issue


def cleanup_action_for_recommendation(issues: list[str], explanation: dict[str, Any]) -> str:
    issue_text = " ".join(issues).lower()
    if "missing supplier" in issue_text or "missing lead time" in issue_text:
        return "update_after_supplier_fix"
    if "missing pack size" in issue_text or "pack-size" in issue_text:
        return "update_after_pack_size_fix" if settings.recommendation_require_pack_size else "review_pack_size_optional"
    if "stale-only" in issue_text or "stale_demand_review_required" in issue_text:
        return "review_stale_demand"
    if "enough stock/no reorder needed" in issue_text:
        return "convert_to_watchlist"
    if "cost missing" in issue_text:
        return "review_missing_cost"
    if "non-positive" in issue_text or explanation.get("purchase_readiness_status") == "blocked":
        return "reject_existing_recommendation"
    return "review"


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
    manager_approved_stale = (
        explanation.get("stale_demand_only")
        and explanation.get("review_decision") == "manager_approved_one_time"
    )
    if explanation.get("stale_demand_only") and not stale_demand_recommendations_allowed() and not manager_approved_stale:
        raise ValueError("Product has stale-only legacy demand and requires manual review.")
    if explanation.get("cost_required") and explanation.get("cost_status") == "missing":
        raise ValueError("Product is missing required cost.")
    if explanation.get("pack_size_required") and explanation.get("pack_size") is None:
        raise ValueError("Product is missing required pack size.")
    if manager_approved_stale:
        if explanation.get("recommended_action") == "reorder" and float(explanation.get("recommended_quantity") or 0) > 0:
            return
        raise ValueError("Product is not currently recommended for reorder.")
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


def parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


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
