from math import ceil

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.usage_history import UsageHistory
from app.services.orderpro_demand import (
    DemandResult,
    calculate_orderpro_demand,
    empty_demand_result,
    product_has_orderpro_history,
)
from app.services.inbound_stock import get_product_inbound_stock
from app.services.seasonality import seasonality_context_for_product


def calculate_reorder_point(avg_daily_usage: float, lead_time_days: int, safety_stock: float) -> float:
    return (avg_daily_usage * lead_time_days) + safety_stock


def calculate_avg_daily_usage(db: Session, product_id: int) -> float:
    return calculate_usage_history_demand(db, product_id).avg_daily_usage


def calculate_usage_history_demand(db: Session, product_id: int) -> DemandResult:
    usage_rows = (
        db.query(UsageHistory)
        .filter(UsageHistory.product_id == product_id)
        .order_by(UsageHistory.date.asc())
        .all()
    )

    if not usage_rows:
        return empty_demand_result("none")

    total_used = sum(row.qty_used for row in usage_rows)
    first_day = usage_rows[0].date
    last_day = usage_rows[-1].date
    day_span = max((last_day - first_day).days + 1, 1)

    return DemandResult(
        avg_daily_usage=round(total_used / day_span, 2),
        demand_source="usage_history",
        demand_lookback_days=None,
        demand_history_start=first_day,
        demand_history_end=last_day,
        observation_days=day_span,
        shipped_units_in_window=round(total_used, 2),
        shipped_order_count=len(usage_rows),
        open_confirmed_units=0.0,
        open_packed_units=0.0,
        open_backorder_units=0.0,
        total_open_demand=0.0,
        units_sold_in_window=round(total_used, 2),
        eligible_order_count=len(usage_rows),
        excluded_order_count=0,
    )


def resolve_demand_context(db: Session, product: Product) -> DemandResult:
    has_orderpro_identity = bool(product.orderpro_id or product.orderpro_sku or product.source_system == "orderpro")
    has_orderpro_rows = product_has_orderpro_history(db, product.id)

    if has_orderpro_identity or has_orderpro_rows:
        orderpro_result = calculate_orderpro_demand(db, product)
        if orderpro_result.eligible_order_count > 0 or orderpro_result.total_open_demand > 0:
            return orderpro_result

        legacy_result = calculate_usage_history_demand(db, product.id)
        if legacy_result.avg_daily_usage > 0:
            return legacy_result
        if has_orderpro_rows:
            return orderpro_result

    return calculate_usage_history_demand(db, product.id)


def resolve_supplier_context(product: Product) -> dict:
    if product.supplier_id and product.supplier_record:
        supplier = product.supplier_record
        lead_time_days, lead_time_source = resolve_orderpro_lead_time(product)
        return {
            "supplier_id": product.supplier_id,
            "supplier_name": supplier.name,
            "supplier_code": supplier.orderpro_code,
            "matched_sku": product.supplier_sku,
            "supplier_sku": product.supplier_sku,
            "supplier_product_name": None,
            "purchase_price": product.cost_price,
            "currency": None,
            "minimum_order_quantity_used": product.min_order_qty,
            "moq_source": "product_record",
            "match_status": None,
            "match_method": None,
            "mapping_source": "orderpro_product_supplier",
            "lead_time_days_used": lead_time_days,
            "lead_time_source": lead_time_source,
        }

    if product.lead_time_days and product.lead_time_days > 0:
        return {
            "supplier_id": None,
            "supplier_name": product.supplier,
            "supplier_code": None,
            "matched_sku": None,
            "supplier_sku": None,
            "supplier_product_name": None,
            "purchase_price": None,
            "currency": None,
            "minimum_order_quantity_used": product.min_order_qty,
            "moq_source": "product_record",
            "match_status": None,
            "match_method": None,
            "mapping_source": "legacy_product",
            "lead_time_days_used": int(product.lead_time_days),
            "lead_time_source": "product_record",
        }

    if product.supplier:
        return {
            **missing_supplier_context(),
            "supplier_name": product.supplier,
            "minimum_order_quantity_used": product.min_order_qty,
            "moq_source": "product_record",
            "mapping_source": "legacy_product",
        }

    return missing_supplier_context()


def resolve_orderpro_lead_time(product: Product) -> tuple[int, str]:
    if product.supplier_record and product.supplier_record.lead_time_days is not None:
        return int(product.supplier_record.lead_time_days), "supplier_record"

    if product.lead_time_days and product.lead_time_days > 0:
        return int(product.lead_time_days), "product_record"

    return 0, "missing"


def missing_supplier_context() -> dict:
    return {
        "supplier_id": None,
        "supplier_name": None,
        "supplier_code": None,
        "matched_sku": None,
        "supplier_sku": None,
        "supplier_product_name": None,
        "purchase_price": None,
        "currency": None,
        "minimum_order_quantity_used": 0,
        "moq_source": "missing",
        "match_status": None,
        "match_method": None,
        "mapping_source": "missing",
        "lead_time_days_used": 0,
        "lead_time_source": "missing",
    }


def resolve_inventory_context(product: Product) -> dict:
    current_stock = round(float(product.current_stock or 0), 2)
    if product.inventory_positions:
        synced_total = round(sum(float(pos.quantity_on_hand or 0) for pos in product.inventory_positions), 2)
        return {
            "current_stock": current_stock,
            "inventory_source": "orderpro_current_stock_cache",
            "has_live_inventory": True,
            "inventory_position_total": synced_total,
        }

    return {
        "current_stock": current_stock,
        "inventory_source": "product_record",
        "has_live_inventory": False,
        "inventory_position_total": None,
    }


def build_supplier_context_response(supplier_ctx: dict) -> dict:
    mapping_source = supplier_ctx["mapping_source"]

    return {
        "supplier_id": supplier_ctx["supplier_id"],
        "supplier_name": supplier_ctx["supplier_name"],
        "supplier_code": supplier_ctx.get("supplier_code"),
        "supplier_sku": supplier_ctx["supplier_sku"],
        "supplier_product_name": supplier_ctx["supplier_product_name"],
        "purchase_price": supplier_ctx["purchase_price"],
        "currency": supplier_ctx["currency"],
        "lead_time_days": supplier_ctx["lead_time_days_used"],
        "lead_time_source": supplier_ctx["lead_time_source"],
        "minimum_order_quantity": supplier_ctx["minimum_order_quantity_used"],
        "moq_source": supplier_ctx["moq_source"],
        "match_status": supplier_ctx["match_status"],
        "match_method": supplier_ctx["match_method"],
        "mapping_source": mapping_source,
        "has_supplier_mapping": mapping_source == "orderpro_product_supplier",
        "needs_supplier_mapping": mapping_source != "orderpro_product_supplier",
    }


def build_forecast(db: Session, product: Product) -> dict:
    if product.is_non_inventory:
        return {
            "product_id": product.id,
            "product_name": product.name,
            "orderpro_sku": product.orderpro_sku,
            "current_stock": product.current_stock,
            "inventory_source": "ignored",
            "avg_daily_usage": 0.0,
            "demand_source": "not_applicable",
            "demand_lookback_days": None,
            "demand_history_start": None,
            "demand_history_end": None,
            "observation_days": None,
            "shipped_units_in_window": 0.0,
            "shipped_order_count": 0,
            "open_confirmed_units": 0.0,
            "open_packed_units": 0.0,
            "open_backorder_units": 0.0,
            "total_open_demand": 0.0,
            "effective_available_stock": 0.0,
            "net_available_stock": 0.0,
            "projected_lead_time_demand": 0.0,
            "total_required_stock": 0.0,
            "incoming_qty": 0.0,
            "effective_available_stock_for_reorder": 0.0,
            "recommended_qty_before_inbound": 0.0,
            "recommended_qty_after_inbound": 0.0,
            "inbound_adjustment_qty": 0.0,
            "units_sold_in_window": 0.0,
            "eligible_order_count": 0,
            "excluded_order_count": 0,
            "days_until_stockout": None,
            "supplier_name": None,
            "matched_sku": None,
            "lead_time_days_used": 0,
            "lead_time_source": "not_applicable",
            "supplier_context": {
                "supplier_id": None,
                "supplier_name": None,
                "supplier_code": None,
                "supplier_sku": None,
                "supplier_product_name": None,
                "purchase_price": None,
                "currency": None,
                "lead_time_days": 0,
                "lead_time_source": "not_applicable",
                "minimum_order_quantity": 0,
                "moq_source": "not_applicable",
                "match_status": None,
                "match_method": None,
                "mapping_source": "not_applicable",
                "has_supplier_mapping": False,
                "needs_supplier_mapping": False,
            },
            "seasonality_context": None,
            "incoming_stock_context": None,
            "reorder_point": 0.0,
            "recommended_action": "ignore",
            "recommended_qty": 0.0,
            "risk_level": "low",
            "explanation": "This row is classified as non-inventory and should not drive purchasing decisions.",
        }

    demand_ctx = resolve_demand_context(db, product)
    avg_daily_usage = demand_ctx.avg_daily_usage
    supplier_ctx = resolve_supplier_context(product)
    inventory_ctx = resolve_inventory_context(product)
    seasonality_context = seasonality_context_for_product(db, product.id)
    incoming_stock_context = get_product_inbound_stock(db, product.id)

    current_stock = inventory_ctx["current_stock"]
    incoming_qty = round(float(incoming_stock_context.get("incoming_qty") or 0), 2)
    effective_available_stock = round(max(current_stock - demand_ctx.total_open_demand, 0), 2)
    net_available_stock = round(current_stock - demand_ctx.total_open_demand, 2)
    effective_available_stock_for_reorder = round(current_stock + incoming_qty - demand_ctx.total_open_demand, 2)
    lead_time_days_used = supplier_ctx["lead_time_days_used"]
    minimum_order_quantity_used = supplier_ctx["minimum_order_quantity_used"]

    projected_lead_time_demand = round(avg_daily_usage * lead_time_days_used, 2)
    reorder_point = round(
        projected_lead_time_demand + float(product.safety_stock or 0),
        2,
    )
    total_required_stock = round(projected_lead_time_demand + demand_ctx.total_open_demand + float(product.safety_stock or 0), 2)
    raw_recommended_qty_before_inbound = max(total_required_stock - current_stock, 0)
    raw_recommended_qty = max(total_required_stock - current_stock - incoming_qty, 0)
    recommended_qty_before_inbound = round_order_quantity(
        max(raw_recommended_qty_before_inbound, minimum_order_quantity_used if raw_recommended_qty_before_inbound > 0 else 0),
        product,
    )
    has_open_demand_shortage = demand_ctx.total_open_demand > (current_stock + incoming_qty)

    if avg_daily_usage > 0:
        days_until_stockout = round(effective_available_stock / avg_daily_usage, 2)
    else:
        days_until_stockout = None

    if raw_recommended_qty > 0:
        recommended_action = "reorder"
        recommended_qty = max(raw_recommended_qty, minimum_order_quantity_used, 0)
        risk_level = "high" if has_open_demand_shortage or effective_available_stock <= reorder_point else "medium"
        explanation_parts = []
        if has_open_demand_shortage:
            explanation_parts.append(
                f"Open committed demand is {demand_ctx.total_open_demand} units, which exceeds current stock plus incoming stock of {current_stock + incoming_qty}."
            )
        if avg_daily_usage > 0:
            explanation_parts.append(
                f"Projected lead-time demand is {projected_lead_time_demand} units and reorder point is {reorder_point}."
            )
        if not explanation_parts:
            explanation_parts.append("Current stock is below required stock for open demand and safety stock.")
        explanation = " ".join(explanation_parts)

    elif incoming_qty > 0 and raw_recommended_qty_before_inbound > 0:
        recommended_action = "monitor"
        recommended_qty = 0.0
        risk_level = "medium" if demand_ctx.total_open_demand > 0 else "low"
        explanation = (
            f"Incoming purchase orders cover the current shortfall. Recommended quantity before inbound stock was "
            f"{recommended_qty_before_inbound}, and incoming stock is {incoming_qty} units."
        )

    elif avg_daily_usage == 0:
        recommended_action = "monitor"
        recommended_qty = 0.0
        risk_level = "medium" if demand_ctx.total_open_demand > 0 else "low"
        if demand_ctx.total_open_demand > 0:
            explanation = (
                f"Open committed demand is {demand_ctx.total_open_demand} units and is covered by current stock, "
                "but no shipped usage history is available yet."
            )
        else:
            explanation = "No usage history is available yet, so the product will be monitored until demand data is collected."

    elif lead_time_days_used <= 0:
        recommended_action = "needs_supplier_mapping"
        recommended_qty = 0.0
        risk_level = "medium"
        explanation = (
            "Demand exists for this product, but there is no usable supplier lead time yet. "
            "Map the product to a supplier with a valid lead time before generating a purchase recommendation."
        )

    else:
        recommended_action = "monitor"
        recommended_qty = 0.0
        risk_level = "low"
        explanation = "Current stock is sufficient based on recent average daily usage."

    recommended_qty = round_order_quantity(recommended_qty, product)
    recommended_qty_after_inbound = recommended_qty
    inbound_adjustment_qty = round(max(recommended_qty_before_inbound - recommended_qty_after_inbound, 0), 2)

    return {
        "product_id": product.id,
        "product_name": product.name,
        "orderpro_sku": product.orderpro_sku,
        "current_stock": current_stock,
        "inventory_source": inventory_ctx["inventory_source"],
        "avg_daily_usage": avg_daily_usage,
        "demand_source": demand_ctx.demand_source,
        "demand_lookback_days": demand_ctx.demand_lookback_days,
        "demand_history_start": demand_ctx.demand_history_start,
        "demand_history_end": demand_ctx.demand_history_end,
        "observation_days": demand_ctx.observation_days,
        "shipped_units_in_window": demand_ctx.shipped_units_in_window,
        "shipped_order_count": demand_ctx.shipped_order_count,
        "open_confirmed_units": demand_ctx.open_confirmed_units,
        "open_packed_units": demand_ctx.open_packed_units,
        "open_backorder_units": demand_ctx.open_backorder_units,
        "total_open_demand": demand_ctx.total_open_demand,
        "effective_available_stock": effective_available_stock,
        "net_available_stock": net_available_stock,
        "projected_lead_time_demand": projected_lead_time_demand,
        "total_required_stock": total_required_stock,
        "incoming_qty": incoming_qty,
        "effective_available_stock_for_reorder": effective_available_stock_for_reorder,
        "recommended_qty_before_inbound": recommended_qty_before_inbound,
        "recommended_qty_after_inbound": recommended_qty_after_inbound,
        "inbound_adjustment_qty": inbound_adjustment_qty,
        "units_sold_in_window": demand_ctx.units_sold_in_window,
        "eligible_order_count": demand_ctx.eligible_order_count,
        "excluded_order_count": demand_ctx.excluded_order_count,
        "days_until_stockout": days_until_stockout,
        "supplier_name": supplier_ctx["supplier_name"],
        "matched_sku": supplier_ctx["matched_sku"],
        "lead_time_days_used": lead_time_days_used,
        "lead_time_source": supplier_ctx["lead_time_source"],
        "supplier_context": build_supplier_context_response(supplier_ctx),
        "seasonality_context": seasonality_context,
        "incoming_stock_context": incoming_stock_context,
        "reorder_point": reorder_point,
        "recommended_action": recommended_action,
        "recommended_qty": recommended_qty,
        "risk_level": risk_level,
        "explanation": explanation,
    }


def round_order_quantity(quantity: float, product: Product) -> float:
    if quantity <= 0:
        return 0.0
    rounded = float(ceil(quantity))
    pack_size = getattr(product, "pack_size", None)
    if pack_size and pack_size > 0:
        rounded = float(ceil(rounded / pack_size) * pack_size)
    return rounded
