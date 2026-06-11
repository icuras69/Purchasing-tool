from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.orderpro_order import OrderProOrderItem
from app.models.orderpro_purchase_order import OrderProPurchaseOrder, OrderProPurchaseOrderLine
from app.models.product import Product
from app.models.product_forecast_input_profile import ProductForecastInputProfile
from app.models.product_supplier import ProductSupplier
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.supplier import Supplier


CALCULATION_VERSION = "forecast-inputs-v1"


@dataclass
class ForecastInputPlan:
    mode: str
    audit: dict[str, Any]
    summary: dict[str, Any]
    samples: dict[str, Any]
    warnings: list[str]


def positive(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def current_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def orderpro_products_query(db: Session):
    return (
        db.query(Product)
        .options(
            selectinload(Product.supplier_record),
            selectinload(Product.forecast_input_profile),
            selectinload(Product.orderpro_order_items),
        )
        .filter(
            (Product.source_system == "orderpro")
            | (Product.orderpro_id.is_not(None))
            | (Product.orderpro_sku.is_not(None))
        )
    )


def effective_forecast_inputs(db: Session, product: Product) -> dict[str, Any]:
    cost_price, cost_source, cost_confidence, cost_updated_at = resolve_cost(db, product)
    lead_time_days, lead_time_source, lead_time_confidence = resolve_lead_time(product)
    min_order_qty, moq_source = resolve_moq(product)
    pack_size, pack_size_source = resolve_pack_size(product)
    safety_stock, safety_stock_source = resolve_safety_stock(product)

    blocking = []
    warnings = []
    if product.supplier_id is None:
        blocking.append("missing_supplier")
    if lead_time_days is None:
        warnings.append("missing_lead_time")
    if cost_price is None:
        warnings.append("missing_cost")
    if pack_size is None:
        warnings.append("missing_pack_size")
    if moq_source == "business_default":
        warnings.append("fallback_moq")
    if lead_time_source == "configured_default":
        warnings.append("fallback_lead_time")

    available_inputs = []
    missing_inputs = []
    for name, present in {
        "supplier_id": product.supplier_id is not None,
        "supplier_sku": bool(product.supplier_sku),
        "cost_price": cost_price is not None,
        "lead_time": lead_time_days is not None,
        "moq": min_order_qty is not None,
        "pack_size": pack_size is not None,
        "safety_stock": safety_stock is not None,
        "current_stock": product.current_stock is not None,
    }.items():
        (available_inputs if present else missing_inputs).append(name)

    readiness_score = round((len(available_inputs) / (len(available_inputs) + len(missing_inputs))) * 100, 2)

    return {
        "product_id": product.id,
        "cost_price": cost_price,
        "cost_source": cost_source,
        "cost_confidence": cost_confidence,
        "cost_updated_at": cost_updated_at,
        "lead_time_days": lead_time_days,
        "lead_time_source": lead_time_source,
        "lead_time_confidence": lead_time_confidence,
        "min_order_qty": min_order_qty,
        "moq_source": moq_source,
        "pack_size": pack_size,
        "pack_size_source": pack_size_source,
        "safety_stock": safety_stock,
        "safety_stock_source": safety_stock_source,
        "blocking_issues": blocking,
        "warning_issues": warnings,
        "available_inputs": sorted(available_inputs),
        "missing_inputs": sorted(missing_inputs),
        "readiness_score": readiness_score,
    }


def resolve_cost(db: Session, product: Product) -> tuple[float | None, str, str, datetime | None]:
    product_cost = positive(product.cost_price)
    if product_cost is not None:
        return product_cost, "orderpro_product_cost", "high", product.last_synced_at

    orderpro_line = latest_orderpro_po_cost_line(db, product.id)
    if orderpro_line is not None and positive(orderpro_line.unit_cost) is not None:
        return positive(orderpro_line.unit_cost), "orderpro_purchase_order_line", "medium", orderpro_line.updated_at

    local_line = latest_local_po_cost_line(db, product.id)
    if local_line is not None and positive(local_line.unit_cost) is not None:
        updated_at = local_line.purchase_order.updated_at if local_line.purchase_order else None
        return positive(local_line.unit_cost), "local_purchase_order_line", "medium", updated_at

    return None, "missing", "missing", None


def latest_orderpro_po_cost_line(db: Session, product_id: int) -> OrderProPurchaseOrderLine | None:
    lines = (
        db.query(OrderProPurchaseOrderLine)
        .join(OrderProPurchaseOrder, OrderProPurchaseOrder.id == OrderProPurchaseOrderLine.orderpro_purchase_order_id)
        .options(selectinload(OrderProPurchaseOrderLine.purchase_order))
        .filter(OrderProPurchaseOrderLine.product_id == product_id, OrderProPurchaseOrderLine.unit_cost.is_not(None))
        .all()
    )
    lines = [line for line in lines if positive(line.unit_cost) is not None]
    return sorted(
        lines,
        key=lambda line: (
            line.purchase_order.order_date if line.purchase_order and line.purchase_order.order_date else datetime.min,
            line.updated_at or datetime.min,
        ),
        reverse=True,
    )[0] if lines else None


def latest_local_po_cost_line(db: Session, product_id: int) -> PurchaseOrderLine | None:
    lines = (
        db.query(PurchaseOrderLine)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .options(selectinload(PurchaseOrderLine.purchase_order))
        .filter(PurchaseOrderLine.product_id == product_id, PurchaseOrderLine.unit_cost.is_not(None))
        .all()
    )
    lines = [line for line in lines if positive(line.unit_cost) is not None]
    return sorted(
        lines,
        key=lambda line: line.purchase_order.updated_at if line.purchase_order and line.purchase_order.updated_at else datetime.min,
        reverse=True,
    )[0] if lines else None


def resolve_lead_time(product: Product) -> tuple[int | None, str, str]:
    if product.lead_time_days and product.lead_time_days > 0:
        return int(product.lead_time_days), "product_record", "high"
    if product.supplier_record and product.supplier_record.lead_time_days and product.supplier_record.lead_time_days > 0:
        return int(product.supplier_record.lead_time_days), "supplier_record", "medium"
    legacy_mapping = best_legacy_product_supplier(product)
    if legacy_mapping and legacy_mapping.lead_time_days and legacy_mapping.lead_time_days > 0:
        return int(legacy_mapping.lead_time_days), "legacy_product_supplier", "low"
    return None, "missing", "missing"


def best_legacy_product_supplier(product: Product) -> ProductSupplier | None:
    mappings = [mapping for mapping in product.product_suppliers if mapping.match_status in {"matched", "confirmed"}]
    return sorted(mappings, key=lambda mapping: (not mapping.is_preferred, mapping.id))[0] if mappings else None


def resolve_moq(product: Product) -> tuple[float, str]:
    moq = positive(product.min_order_qty)
    if moq is not None:
        return moq, "product_record"
    return 1.0, "business_default"


def resolve_pack_size(product: Product) -> tuple[float | None, str]:
    pack_size = positive(getattr(product, "pack_size", None))
    if pack_size is not None:
        return pack_size, "product_record"
    return None, "missing"


def resolve_safety_stock(product: Product) -> tuple[float, str]:
    if product.safety_stock is not None:
        return float(product.safety_stock), "product_record"
    return 0.0, "business_default"


def profile_fields_from_effective(effective: dict[str, Any], *, calculated_at: datetime, calculation_version: str) -> dict[str, Any]:
    return {
        "cost_price": effective["cost_price"],
        "cost_source": effective["cost_source"],
        "cost_confidence": effective["cost_confidence"],
        "cost_updated_at": effective["cost_updated_at"],
        "lead_time_days": effective["lead_time_days"],
        "lead_time_source": effective["lead_time_source"],
        "lead_time_confidence": effective["lead_time_confidence"],
        "min_order_qty": effective["min_order_qty"],
        "moq_source": effective["moq_source"],
        "pack_size": effective["pack_size"],
        "pack_size_source": effective["pack_size_source"],
        "safety_stock": effective["safety_stock"],
        "safety_stock_source": effective["safety_stock_source"],
        "blocking_issues": effective["blocking_issues"],
        "warning_issues": effective["warning_issues"],
        "readiness_score": effective["readiness_score"],
        "calculation_version": calculation_version,
        "calculated_at": calculated_at,
        "updated_at": calculated_at,
    }


def plan_forecast_input_reconciliation(
    db: Session,
    *,
    product_id: int | None = None,
    supplier_id: int | None = None,
    calculation_version: str = CALCULATION_VERSION,
) -> ForecastInputPlan:
    products = filtered_products(db, product_id=product_id, supplier_id=supplier_id)
    effective_by_product = {product.id: effective_forecast_inputs(db, product) for product in products}
    existing_profiles = {
        profile.product_id: profile
        for profile in db.query(ProductForecastInputProfile)
        .filter(ProductForecastInputProfile.product_id.in_(effective_by_product) if effective_by_product else False)
        .all()
    }

    samples_improved = []
    samples_blocked = []
    profiles_to_create = 0
    profiles_to_update = 0
    source_counts = {
        "cost_source_counts": Counter(),
        "lead_time_source_counts": Counter(),
        "moq_source_counts": Counter(),
        "pack_size_source_counts": Counter(),
    }

    for product in products:
        effective = effective_by_product[product.id]
        for key, source_key in (
            ("cost_source_counts", "cost_source"),
            ("lead_time_source_counts", "lead_time_source"),
            ("moq_source_counts", "moq_source"),
            ("pack_size_source_counts", "pack_size_source"),
        ):
            source_counts[key][effective[source_key]] += 1

        existing = existing_profiles.get(product.id)
        if existing is None:
            profiles_to_create += 1
        elif profile_needs_update(existing, effective, calculation_version):
            profiles_to_update += 1

        if effective["cost_source"] != "missing" or effective["lead_time_source"] != "missing":
            if len(samples_improved) < 10:
                samples_improved.append(product_sample(product, effective))
        if effective["blocking_issues"] or "missing_cost" in effective["warning_issues"] or "missing_lead_time" in effective["warning_issues"]:
            if len(samples_blocked) < 10:
                samples_blocked.append(product_sample(product, effective))

    summary = {
        "products_evaluated": len(products),
        "profiles_to_create": profiles_to_create,
        "profiles_to_update": profiles_to_update,
        "products_that_would_gain_cost": sum(1 for item in effective_by_product.values() if item["cost_source"] != "missing"),
        "products_that_would_gain_lead_time": sum(1 for item in effective_by_product.values() if item["lead_time_source"] != "missing"),
        "products_that_would_gain_moq": sum(1 for item in effective_by_product.values() if item["moq_source"] != "missing"),
        "products_that_would_gain_pack_size": sum(1 for item in effective_by_product.values() if item["pack_size_source"] != "missing"),
        "products_still_missing_supplier": sum(1 for item in effective_by_product.values() if "missing_supplier" in item["blocking_issues"]),
        "products_still_missing_cost": sum(1 for item in effective_by_product.values() if "missing_cost" in item["warning_issues"]),
        "products_still_missing_lead_time": sum(1 for item in effective_by_product.values() if "missing_lead_time" in item["warning_issues"]),
        "products_using_fallback_moq": sum(1 for item in effective_by_product.values() if item["moq_source"] == "business_default"),
        "readiness_score_average": round(
            sum(item["readiness_score"] for item in effective_by_product.values()) / len(effective_by_product),
            2,
        )
        if effective_by_product
        else 0,
        **{key: dict(value) for key, value in source_counts.items()},
        "top_blocking_issues": dict(Counter(issue for item in effective_by_product.values() for issue in item["blocking_issues"])),
    }

    return ForecastInputPlan(
        mode="dry_run",
        audit=forecast_input_audit(db, products=products),
        summary=summary,
        samples={"improved": samples_improved, "still_blocked": samples_blocked},
        warnings=[],
    )


def apply_forecast_input_reconciliation(
    db: Session,
    *,
    product_id: int | None = None,
    supplier_id: int | None = None,
    calculation_version: str = CALCULATION_VERSION,
) -> ForecastInputPlan:
    plan = plan_forecast_input_reconciliation(
        db,
        product_id=product_id,
        supplier_id=supplier_id,
        calculation_version=calculation_version,
    )
    now = current_utc_naive()
    products = filtered_products(db, product_id=product_id, supplier_id=supplier_id)
    profiles = {profile.product_id: profile for profile in db.query(ProductForecastInputProfile).all()}
    created = 0
    updated = 0
    for product in products:
        effective = effective_forecast_inputs(db, product)
        fields = profile_fields_from_effective(effective, calculated_at=now, calculation_version=calculation_version)
        profile = profiles.get(product.id)
        if profile is None:
            profile = ProductForecastInputProfile(product_id=product.id, created_at=now, **fields)
            db.add(profile)
            created += 1
        else:
            if profile_needs_update(profile, effective, calculation_version):
                for key, value in fields.items():
                    setattr(profile, key, value)
                updated += 1
    db.commit()
    plan.mode = "apply"
    plan.summary["profiles_created"] = created
    plan.summary["profiles_updated"] = updated
    return plan


def filtered_products(db: Session, *, product_id: int | None = None, supplier_id: int | None = None) -> list[Product]:
    query = orderpro_products_query(db).options(selectinload(Product.product_suppliers))
    if product_id is not None:
        query = query.filter(Product.id == product_id)
    if supplier_id is not None:
        query = query.filter(Product.supplier_id == supplier_id)
    return query.order_by(Product.id.asc()).all()


def profile_needs_update(profile: ProductForecastInputProfile, effective: dict[str, Any], calculation_version: str) -> bool:
    fields = profile_fields_from_effective(effective, calculated_at=profile.calculated_at, calculation_version=calculation_version)
    return any(normalize(getattr(profile, key, None)) != normalize(value) for key, value in fields.items() if key not in {"calculated_at", "updated_at"})


def normalize(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    return value


def product_sample(product: Product, effective: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": product.id,
        "orderpro_sku": product.orderpro_sku,
        "name": product.name,
        "supplier_id": product.supplier_id,
        "cost_price": effective["cost_price"],
        "cost_source": effective["cost_source"],
        "lead_time_days": effective["lead_time_days"],
        "lead_time_source": effective["lead_time_source"],
        "min_order_qty": effective["min_order_qty"],
        "moq_source": effective["moq_source"],
        "pack_size": effective["pack_size"],
        "pack_size_source": effective["pack_size_source"],
        "blocking_issues": effective["blocking_issues"],
        "warning_issues": effective["warning_issues"],
    }


def forecast_input_audit(db: Session, *, products: list[Product] | None = None) -> dict[str, Any]:
    products = products if products is not None else orderpro_products_query(db).all()
    effective = [effective_forecast_inputs(db, product) for product in products]
    suppliers = db.query(Supplier).all()
    orderpro_po_product_ids = {
        line.product_id
        for line in db.query(OrderProPurchaseOrderLine).filter(OrderProPurchaseOrderLine.unit_cost.is_not(None)).all()
        if line.product_id is not None and positive(line.unit_cost) is not None
    }
    local_po_product_ids = {
        line.product_id
        for line in db.query(PurchaseOrderLine).filter(PurchaseOrderLine.unit_cost.is_not(None)).all()
        if positive(line.unit_cost) is not None
    }
    demand_product_ids = {
        item.product_id
        for item in db.query(OrderProOrderItem).all()
        if item.product_id is not None
    }
    supplier_product_counts = Counter(product.supplier_id for product in products if product.supplier_id is not None)

    return {
        "total_orderpro_products": len(products),
        "products_with_cost_price": sum(1 for product in products if positive(product.cost_price) is not None),
        "products_missing_cost_price": sum(1 for item in effective if item["cost_source"] == "missing"),
        "products_with_supplier_id": sum(1 for product in products if product.supplier_id is not None),
        "products_missing_supplier_id": sum(1 for product in products if product.supplier_id is None),
        "products_with_supplier_sku": sum(1 for product in products if product.supplier_sku),
        "products_missing_supplier_sku": sum(1 for product in products if not product.supplier_sku),
        "products_with_lead_time_days_directly": sum(1 for product in products if product.lead_time_days and product.lead_time_days > 0),
        "products_inheriting_lead_time_from_supplier": sum(1 for item in effective if item["lead_time_source"] == "supplier_record"),
        "products_missing_usable_lead_time": sum(1 for item in effective if item["lead_time_source"] == "missing"),
        "products_with_moq": sum(1 for item in effective if item["moq_source"] != "missing"),
        "products_missing_moq": sum(1 for item in effective if item["moq_source"] == "missing"),
        "products_using_fallback_moq": sum(1 for item in effective if item["moq_source"] == "business_default"),
        "products_with_pack_size": sum(1 for item in effective if item["pack_size_source"] != "missing"),
        "products_missing_pack_size": sum(1 for item in effective if item["pack_size_source"] == "missing"),
        "products_with_safety_stock": sum(1 for product in products if product.safety_stock is not None),
        "products_missing_safety_stock": sum(1 for product in products if product.safety_stock is None),
        "products_with_recent_po_unit_cost": len(orderpro_po_product_ids | local_po_product_ids),
        "products_with_orderpro_cost_price": sum(1 for item in effective if item["cost_source"] == "orderpro_product_cost"),
        "products_with_po_derived_cost": sum(
            1
            for item in effective
            if item["cost_source"] in {"orderpro_purchase_order_line", "local_purchase_order_line"}
        ),
        "products_where_cost_sources_disagree": cost_disagreement_count(db, products),
        "suppliers_with_lead_time": sum(1 for supplier in suppliers if supplier.lead_time_days and supplier.lead_time_days > 0),
        "suppliers_missing_lead_time": sum(1 for supplier in suppliers if not supplier.lead_time_days or supplier.lead_time_days <= 0),
        "suppliers_with_no_products": sum(1 for supplier in suppliers if supplier_product_counts.get(supplier.id, 0) == 0),
        "products_with_supplier_assigned_but_supplier_missing_lead_time": sum(
            1
            for product in products
            if product.supplier_id is not None
            and (not product.supplier_record or not product.supplier_record.lead_time_days or product.supplier_record.lead_time_days <= 0)
            and not (product.lead_time_days and product.lead_time_days > 0)
        ),
        "products_with_historical_demand_but_missing_supplier_cost_or_lead_time": sum(
            1
            for product, item in zip(products, effective)
            if product.id in demand_product_ids
            and (
                "missing_supplier" in item["blocking_issues"]
                or "missing_cost" in item["warning_issues"]
                or "missing_lead_time" in item["warning_issues"]
            )
        ),
    }


def cost_disagreement_count(db: Session, products: list[Product]) -> int:
    count = 0
    for product in products:
        product_cost = positive(product.cost_price)
        po_line = latest_orderpro_po_cost_line(db, product.id) or latest_local_po_cost_line(db, product.id)
        po_cost = positive(po_line.unit_cost) if po_line is not None else None
        if product_cost is not None and po_cost is not None and round(product_cost, 4) != round(po_cost, 4):
            count += 1
    return count


def profile_or_effective_inputs(db: Session, product: Product) -> dict[str, Any]:
    return effective_forecast_inputs(db, product)
