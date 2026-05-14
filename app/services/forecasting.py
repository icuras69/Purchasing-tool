from math import ceil

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.usage_history import UsageHistory


def calculate_reorder_point(avg_daily_usage: float, lead_time_days: int, safety_stock: float) -> float:
    return (avg_daily_usage * lead_time_days) + safety_stock


def calculate_avg_daily_usage(db: Session, product_id: int) -> float:
    usage_rows = (
        db.query(UsageHistory)
        .filter(UsageHistory.product_id == product_id)
        .order_by(UsageHistory.date.asc())
        .all()
    )

    if not usage_rows:
        return 0.0

    total_used = sum(row.qty_used for row in usage_rows)
    first_day = usage_rows[0].date
    last_day = usage_rows[-1].date
    day_span = max((last_day - first_day).days + 1, 1)

    return round(total_used / day_span, 2)


def resolve_supplier_context(product: Product) -> dict:
    linked_items = [item for item in product.master_items if item.supplier_id and item.supplier]

    preferred = None
    if linked_items:
        preferred = next((item for item in linked_items if item.match_status == "matched"), linked_items[0])

    if preferred and preferred.supplier and preferred.supplier.lead_time_days is not None:
        return {
            "supplier_name": preferred.supplier.name,
            "matched_sku": preferred.sku,
            "lead_time_days_used": int(preferred.supplier.lead_time_days),
            "lead_time_source": "supplier_master",
        }

    if preferred and preferred.supplier:
        return {
            "supplier_name": preferred.supplier.name,
            "matched_sku": preferred.sku,
            "lead_time_days_used": 0,
            "lead_time_source": "supplier_missing_lead_time",
        }

    if product.lead_time_days and product.lead_time_days > 0:
        return {
            "supplier_name": product.supplier,
            "matched_sku": None,
            "lead_time_days_used": int(product.lead_time_days),
            "lead_time_source": "product_record",
        }

    return {
        "supplier_name": None,
        "matched_sku": None,
        "lead_time_days_used": 0,
        "lead_time_source": "missing",
    }


def resolve_inventory_context(product: Product) -> dict:
    if product.inventory_positions:
        preferred = next(
            (pos for pos in product.inventory_positions if pos.source_system.lower() == "orderpro"),
            product.inventory_positions[0],
        )

        available = preferred.available
        if available is None:
            available = preferred.on_hand - preferred.allocated + preferred.incoming

        location = preferred.location_code or preferred.location_name or "default"

        return {
            "current_stock": round(float(available), 2),
            "inventory_source": f"{preferred.source_system}:{location}",
            "has_live_inventory": True,
        }

    return {
        "current_stock": round(float(product.current_stock or 0), 2),
        "inventory_source": "product_record",
        "has_live_inventory": False,
    }


def build_forecast(db: Session, product: Product) -> dict:
    if product.is_non_inventory:
        return {
            "product_id": product.id,
            "product_name": product.name,
            "current_stock": product.current_stock,
            "inventory_source": "ignored",
            "avg_daily_usage": 0.0,
            "days_until_stockout": None,
            "supplier_name": None,
            "matched_sku": None,
            "lead_time_days_used": 0,
            "lead_time_source": "not_applicable",
            "reorder_point": 0.0,
            "recommended_action": "ignore",
            "recommended_qty": 0.0,
            "risk_level": "low",
            "explanation": "This row is classified as non-inventory and should not drive purchasing decisions.",
        }

    avg_daily_usage = calculate_avg_daily_usage(db, product.id)
    supplier_ctx = resolve_supplier_context(product)
    inventory_ctx = resolve_inventory_context(product)

    current_stock = inventory_ctx["current_stock"]
    lead_time_days_used = supplier_ctx["lead_time_days_used"]

    reorder_point = round(
        calculate_reorder_point(avg_daily_usage, lead_time_days_used, product.safety_stock),
        2,
    )

    if avg_daily_usage > 0:
        days_until_stockout = round(current_stock / avg_daily_usage, 2)
    else:
        days_until_stockout = None

    if avg_daily_usage == 0:
        recommended_action = "monitor"
        recommended_qty = 0.0
        risk_level = "low"
        explanation = "No usage history is available yet, so the product will be monitored until demand data is collected."

    elif lead_time_days_used <= 0:
        recommended_action = "needs_supplier_mapping"
        recommended_qty = 0.0
        risk_level = "medium"
        explanation = (
            "Demand exists for this product, but there is no usable supplier lead time yet. "
            "Map the product to a supplier with a valid lead time before generating a purchase recommendation."
        )

    elif not inventory_ctx["has_live_inventory"] and current_stock == 0:
        recommended_action = "needs_inventory_sync"
        recommended_qty = 0.0
        risk_level = "medium"
        explanation = (
            "Demand history and supplier lead time are available, but live stock has not been synced from OrderPro yet. "
            "Current stock is still the default value of 0, so no purchase order should be generated from this number alone."
        )

    elif current_stock <= reorder_point:
        recommended_action = "order_now"
        raw_qty = ((lead_time_days_used + 7) * avg_daily_usage) - current_stock
        recommended_qty = max(raw_qty, product.min_order_qty, 0)
        risk_level = "high"
        explanation = (
            f"Current stock is at or below the reorder point. "
            f"Stock covers about {days_until_stockout} days while lead time is {lead_time_days_used} days."
        )

    elif days_until_stockout is not None and days_until_stockout <= lead_time_days_used + 2:
        recommended_action = "order_soon"
        raw_qty = ((lead_time_days_used + 7) * avg_daily_usage) - current_stock
        recommended_qty = max(raw_qty, product.min_order_qty, 0)
        risk_level = "medium"
        explanation = (
            f"Stock is above the reorder point but may run out soon. "
            f"Estimated stock coverage is {days_until_stockout} days."
        )

    else:
        recommended_action = "monitor"
        recommended_qty = 0.0
        risk_level = "low"
        explanation = "Current stock is sufficient based on recent average daily usage."

    recommended_qty = float(ceil(recommended_qty)) if recommended_qty > 0 else 0.0

    return {
        "product_id": product.id,
        "product_name": product.name,
        "current_stock": current_stock,
        "inventory_source": inventory_ctx["inventory_source"],
        "avg_daily_usage": avg_daily_usage,
        "days_until_stockout": days_until_stockout,
        "supplier_name": supplier_ctx["supplier_name"],
        "matched_sku": supplier_ctx["matched_sku"],
        "lead_time_days_used": lead_time_days_used,
        "lead_time_source": supplier_ctx["lead_time_source"],
        "reorder_point": reorder_point,
        "recommended_action": recommended_action,
        "recommended_qty": recommended_qty,
        "risk_level": risk_level,
        "explanation": explanation,
    }