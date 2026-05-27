from math import ceil

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product_supplier import ProductSupplier
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
    product_supplier = select_product_supplier(product)
    if product_supplier:
        return product_supplier_context(product, product_supplier)

    if product.product_suppliers:
        return missing_supplier_context()

    linked_items = [item for item in product.master_items if item.supplier_id and item.supplier]
    preferred = None
    if linked_items:
        preferred = next((item for item in linked_items if item.match_status == "matched"), linked_items[0])

    if preferred and preferred.supplier and preferred.supplier.lead_time_days is not None:
        return {
            "supplier_id": preferred.supplier_id,
            "supplier_name": preferred.supplier.name,
            "matched_sku": preferred.sku,
            "supplier_sku": preferred.sku,
            "supplier_product_name": preferred.name,
            "purchase_price": preferred.cost_price,
            "currency": None,
            "minimum_order_quantity_used": product.min_order_qty,
            "match_status": preferred.match_status,
            "match_method": preferred.match_method,
            "mapping_source": "product_master_item",
            "lead_time_days_used": int(preferred.supplier.lead_time_days),
            "lead_time_source": "supplier_master",
        }

    if preferred and preferred.supplier:
        return {
            "supplier_id": preferred.supplier_id,
            "supplier_name": preferred.supplier.name,
            "matched_sku": preferred.sku,
            "supplier_sku": preferred.sku,
            "supplier_product_name": preferred.name,
            "purchase_price": preferred.cost_price,
            "currency": None,
            "minimum_order_quantity_used": product.min_order_qty,
            "match_status": preferred.match_status,
            "match_method": preferred.match_method,
            "mapping_source": "product_master_item",
            "lead_time_days_used": 0,
            "lead_time_source": "supplier_missing_lead_time",
        }

    if product.lead_time_days and product.lead_time_days > 0:
        return {
            "supplier_id": None,
            "supplier_name": product.supplier,
            "matched_sku": None,
            "supplier_sku": None,
            "supplier_product_name": None,
            "purchase_price": None,
            "currency": None,
            "minimum_order_quantity_used": product.min_order_qty,
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
            "mapping_source": "legacy_product",
        }

    return missing_supplier_context()


def select_product_supplier(product: Product) -> ProductSupplier | None:
    mappings = list(product.product_suppliers)
    if not mappings:
        return None

    preferred = next((mapping for mapping in mappings if mapping.is_preferred), None)
    if preferred:
        return preferred

    matched = [mapping for mapping in mappings if mapping.match_status == "matched"]
    if matched:
        return sorted(matched, key=lambda mapping: mapping.id or 0)[0]

    return None


def product_supplier_context(product: Product, product_supplier: ProductSupplier) -> dict:
    supplier = product_supplier.supplier
    lead_time_days, lead_time_source = resolve_lead_time(product, product_supplier)
    minimum_order_quantity = (
        product_supplier.minimum_order_quantity
        if product_supplier.minimum_order_quantity is not None
        else product.min_order_qty
    )

    return {
        "supplier_id": product_supplier.supplier_id,
        "supplier_name": supplier.name if supplier else None,
        "matched_sku": product_supplier.supplier_sku,
        "supplier_sku": product_supplier.supplier_sku,
        "supplier_product_name": product_supplier.supplier_product_name,
        "purchase_price": product_supplier.purchase_price,
        "currency": product_supplier.currency,
        "minimum_order_quantity_used": minimum_order_quantity,
        "match_status": product_supplier.match_status,
        "match_method": product_supplier.match_method,
        "mapping_source": "product_supplier",
        "lead_time_days_used": lead_time_days,
        "lead_time_source": lead_time_source,
    }


def resolve_lead_time(product: Product, product_supplier: ProductSupplier) -> tuple[int, str]:
    if product_supplier.lead_time_days is not None:
        return int(product_supplier.lead_time_days), "product_supplier"

    if product_supplier.supplier and product_supplier.supplier.lead_time_days is not None:
        return int(product_supplier.supplier.lead_time_days), "supplier_master"

    if product.lead_time_days and product.lead_time_days > 0:
        return int(product.lead_time_days), "product_record"

    return 0, "missing"


def missing_supplier_context() -> dict:
    return {
        "supplier_id": None,
        "supplier_name": None,
        "matched_sku": None,
        "supplier_sku": None,
        "supplier_product_name": None,
        "purchase_price": None,
        "currency": None,
        "minimum_order_quantity_used": 0,
        "match_status": None,
        "match_method": None,
        "mapping_source": "missing",
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
        "reorder_point": reorder_point,
        "recommended_action": recommended_action,
        "recommended_qty": recommended_qty,
        "risk_level": risk_level,
        "explanation": explanation,
    }
