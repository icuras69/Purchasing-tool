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
            "current_stock": product.current_stock,
            "inventory_source": "ignored",
            "avg_daily_usage": 0.0,
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
    minimum_order_quantity_used = supplier_ctx["minimum_order_quantity_used"]

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
        recommended_qty = max(raw_qty, minimum_order_quantity_used, 0)
        risk_level = "high"
        explanation = (
            f"Current stock is at or below the reorder point. "
            f"Stock covers about {days_until_stockout} days while lead time is {lead_time_days_used} days."
        )

    elif days_until_stockout is not None and days_until_stockout <= lead_time_days_used + 2:
        recommended_action = "order_soon"
        raw_qty = ((lead_time_days_used + 7) * avg_daily_usage) - current_stock
        recommended_qty = max(raw_qty, minimum_order_quantity_used, 0)
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
        "supplier_context": build_supplier_context_response(supplier_ctx),
        "reorder_point": reorder_point,
        "recommended_action": recommended_action,
        "recommended_qty": recommended_qty,
        "risk_level": risk_level,
        "explanation": explanation,
    }
