from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import io
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.orderpro_order import OrderProOrderItem
from app.models.orderpro_purchase_order import OrderProPurchaseOrder, OrderProPurchaseOrderLine
from app.models.product import Product
from app.models.product_forecast_input_profile import ProductForecastInputProfile
from app.models.product_supplier import ProductSupplier
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.supplier import Supplier
from app.services.product_search import filter_product_rows_by_search


CALCULATION_VERSION = "forecast-inputs-v1"
READINESS_CSV_COLUMNS = [
    "product_id",
    "sku",
    "product_name",
    "supplier_id",
    "supplier_code",
    "supplier_name",
    "current_stock",
    "demand_history_status",
    "lead_time",
    "cost",
    "pack_size",
    "readiness_score",
    "readiness_status",
    "missing_inputs",
    "warnings",
    "demand_source",
    "supplier_source",
    "stock_source",
    "cost_source",
    "recommendation_status",
    "recommended_quantity",
]


@dataclass
class ForecastInputPlan:
    mode: str
    audit: dict[str, Any]
    summary: dict[str, Any]
    samples: dict[str, Any]
    warnings: list[str]


@dataclass
class ForecastReconciliationCsv:
    content: bytes
    filename: str
    content_type: str = "text/csv; charset=utf-8"


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


def evaluate_product_readiness(db: Session, product: Product) -> dict[str, Any]:
    from app.services.forecasting import build_forecast

    effective = profile_or_effective_inputs(db, product)
    try:
        forecast = build_forecast(db, product)
    except Exception:
        forecast = {}

    supplier = product.supplier_record
    review = product.supplier_assignment_review
    supplier_source = "missing"
    if product.supplier_id is not None:
        supplier_source = "orderpro_product_supplier"
        if review and review.status == "confirmed" and review.suggestion_source == "manual_supplier_cleanup":
            supplier_source = "manual_supplier_cleanup"

    demand_source = forecast.get("demand_source") or "none"
    shipped_units = float(forecast.get("shipped_units_in_window") or forecast.get("units_sold_in_window") or 0)
    open_demand = float(forecast.get("total_open_demand") or 0)
    has_demand_history = shipped_units > 0
    has_demand_signal = has_demand_history or open_demand > 0

    missing_inputs = set(effective["missing_inputs"])
    warnings = set(effective["warning_issues"])
    blocking = set(effective["blocking_issues"])

    if not (product.orderpro_sku or product.orderpro_id or product.source_key):
        missing_inputs.add("product_identifier")
        blocking.add("missing_product_identifier")
    if product.current_stock is None:
        missing_inputs.add("current_stock")
        blocking.add("missing_stock")
    if not has_demand_history:
        missing_inputs.add("demand_history")
        warnings.add("missing_demand_history")

    if blocking:
        status = "blocked"
    elif not has_demand_signal:
        status = "monitor_only"
    elif warnings:
        status = "partially_ready"
    else:
        status = "ready"

    all_inputs = {
        "supplier",
        "lead_time",
        "current_stock",
        "demand_history",
        "cost_price",
        "pack_size",
        "product_identifier",
        "moq",
        "safety_stock",
    }
    present_inputs = {
        "supplier": product.supplier_id is not None,
        "lead_time": effective["lead_time_days"] is not None,
        "current_stock": product.current_stock is not None,
        "demand_history": has_demand_history,
        "cost_price": effective["cost_price"] is not None,
        "pack_size": effective["pack_size"] is not None,
        "product_identifier": bool(product.orderpro_sku or product.orderpro_id or product.source_key),
        "moq": effective["min_order_qty"] is not None,
        "safety_stock": effective["safety_stock"] is not None,
    }
    score = round(sum(1 for present in present_inputs.values() if present) / len(all_inputs) * 100, 2)

    recommended_qty = forecast.get("recommended_qty")
    recommendation_status = forecast.get("recommended_action")
    explanation = _readiness_explanation(status, sorted(missing_inputs), sorted(warnings), recommendation_status)

    return {
        "product_id": product.id,
        "sku": product.orderpro_sku or product.source_key,
        "orderpro_sku": product.orderpro_sku,
        "product_name": product.name,
        "description": product.description,
        "barcode": product.barcode,
        "supplier_id": product.supplier_id,
        "supplier_code": supplier.orderpro_code if supplier else None,
        "supplier_name": supplier.name if supplier else None,
        "supplier_source": supplier_source,
        "current_stock": product.current_stock,
        "stock_source": forecast.get("inventory_source") or "product_current_stock_cache",
        "demand_history_available": has_demand_history,
        "demand_source": demand_source,
        "open_customer_demand": open_demand,
        "lead_time_days": effective["lead_time_days"],
        "lead_time_source": effective["lead_time_source"],
        "cost_price": effective["cost_price"],
        "cost_source": effective["cost_source"],
        "pack_size": effective["pack_size"],
        "pack_size_source": effective["pack_size_source"],
        "min_order_qty": effective["min_order_qty"],
        "moq_source": effective["moq_source"],
        "seasonality_status": _seasonality_status(product),
        "readiness_score": score,
        "readiness_status": status,
        "missing_inputs": sorted(missing_inputs),
        "warnings": sorted(warnings),
        "blocking_issues": sorted(blocking),
        "recommendation_status": recommendation_status,
        "recommended_quantity": recommended_qty,
        "explanation": explanation,
        "sources": {
            "supplier": supplier_source,
            "lead_time": effective["lead_time_source"],
            "stock": forecast.get("inventory_source") or "product_current_stock_cache",
            "demand": demand_source,
            "cost": effective["cost_source"],
            "pack_size": effective["pack_size_source"],
            "seasonality": _seasonality_status(product),
        },
        "inputs": _readiness_inputs(product, supplier, effective, forecast, supplier_source, has_demand_history),
    }


def list_readiness_candidates(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
    status: str | None = None,
    missing_input: str | None = None,
    supplier_id: int | None = None,
    has_open_demand: bool | None = None,
    has_stock: bool | None = None,
    sort_by: str = "readiness_score",
    sort_direction: str = "asc",
) -> dict[str, Any]:
    products = filtered_products(db, supplier_id=supplier_id)
    rows = [evaluate_product_readiness(db, product) for product in products]
    summary = get_readiness_summary(db, rows=rows)
    rows = _filter_readiness_rows(
        rows,
        search=search,
        status=status,
        missing_input=missing_input,
        has_open_demand=has_open_demand,
        has_stock=has_stock,
    )
    rows = _sort_readiness_rows(rows, sort_by=sort_by, sort_direction=sort_direction)
    page = max(page, 1)
    page_size = min(max(page_size, 1), 250)
    total = len(rows)
    total_pages = (total + page_size - 1) // page_size if total else 0
    start = (page - 1) * page_size
    return {
        "items": rows[start : start + page_size],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "summary": summary,
    }


def get_readiness_summary(db: Session, *, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if rows is None:
        rows = [evaluate_product_readiness(db, product) for product in filtered_products(db)]
    total = len(rows)
    ready_like = sum(1 for row in rows if row["readiness_status"] in {"ready", "partially_ready", "monitor_only"})
    return {
        "total_products": total,
        "ready": sum(1 for row in rows if row["readiness_status"] == "ready"),
        "partially_ready": sum(1 for row in rows if row["readiness_status"] == "partially_ready"),
        "blocked": sum(1 for row in rows if row["readiness_status"] == "blocked"),
        "monitor_only": sum(1 for row in rows if row["readiness_status"] == "monitor_only"),
        "missing_supplier": sum(1 for row in rows if "supplier_id" in row["missing_inputs"] or "missing_supplier" in row["blocking_issues"]),
        "missing_lead_time": sum(1 for row in rows if "lead_time" in row["missing_inputs"] or "missing_lead_time" in row["warnings"]),
        "missing_cost": sum(1 for row in rows if "cost_price" in row["missing_inputs"] or "missing_cost" in row["warnings"]),
        "missing_pack_size": sum(1 for row in rows if "pack_size" in row["missing_inputs"] or "missing_pack_size" in row["warnings"]),
        "missing_demand_history": sum(1 for row in rows if "demand_history" in row["missing_inputs"]),
        "missing_stock": sum(1 for row in rows if "current_stock" in row["missing_inputs"]),
        "readiness_percentage": round((ready_like / total) * 100, 2) if total else 0,
    }


def get_product_readiness_detail(db: Session, product_id: int) -> dict[str, Any] | None:
    product = filtered_products(db, product_id=product_id)
    if not product:
        return None
    readiness = evaluate_product_readiness(db, product[0])
    return {
        "product_id": readiness["product_id"],
        "readiness": {
            "score": readiness["readiness_score"],
            "status": readiness["readiness_status"],
            "explanation": readiness["explanation"],
        },
        **readiness,
    }


def build_readiness_csv(
    db: Session,
    *,
    search: str | None = None,
    status: str | None = None,
    missing_input: str | None = None,
    supplier_id: int | None = None,
    has_open_demand: bool | None = None,
    has_stock: bool | None = None,
    sort_by: str = "readiness_score",
    sort_direction: str = "asc",
) -> ForecastReconciliationCsv:
    result = list_readiness_candidates(
        db,
        page=1,
        page_size=100000,
        search=search,
        status=status,
        missing_input=missing_input,
        supplier_id=supplier_id,
        has_open_demand=has_open_demand,
        has_stock=has_stock,
        sort_by=sort_by,
        sort_direction=sort_direction,
    )
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=READINESS_CSV_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    for row in result["items"]:
        writer.writerow(
            {
                "product_id": row["product_id"],
                "sku": safe_csv_text(row["sku"]),
                "product_name": safe_csv_text(row["product_name"]),
                "supplier_id": row["supplier_id"],
                "supplier_code": safe_csv_text(row["supplier_code"]),
                "supplier_name": safe_csv_text(row["supplier_name"]),
                "current_stock": row["current_stock"],
                "demand_history_status": "available" if row["demand_history_available"] else "missing",
                "lead_time": row["lead_time_days"],
                "cost": row["cost_price"],
                "pack_size": row["pack_size"],
                "readiness_score": row["readiness_score"],
                "readiness_status": row["readiness_status"],
                "missing_inputs": "; ".join(row["missing_inputs"]),
                "warnings": "; ".join(row["warnings"]),
                "demand_source": row["demand_source"],
                "supplier_source": row["supplier_source"],
                "stock_source": row["stock_source"],
                "cost_source": row["cost_source"],
                "recommendation_status": row["recommendation_status"],
                "recommended_quantity": row["recommended_quantity"],
            }
        )
    filename = f"forecast_readiness_{datetime.now(timezone.utc).date().isoformat()}.csv"
    return ForecastReconciliationCsv(content=("\ufeff" + handle.getvalue()).encode("utf-8"), filename=filename)


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


def _seasonality_status(product: Product) -> str:
    profile = product.seasonality_profile
    if profile is None:
        return "missing"
    if profile.seasonality_tag == "insufficient_data":
        return "insufficient_data"
    return profile.seasonality_tag or "available"


def _readiness_inputs(
    product: Product,
    supplier: Supplier | None,
    effective: dict[str, Any],
    forecast: dict[str, Any],
    supplier_source: str,
    has_demand_history: bool,
) -> dict[str, Any]:
    return {
        "supplier": {
            "value": supplier.name if supplier else None,
            "supplier_id": product.supplier_id,
            "source": supplier_source,
            "is_missing": product.supplier_id is None,
            "is_fallback": False,
            "blocks_forecast": product.supplier_id is None,
        },
        "lead_time_days": {
            "value": effective["lead_time_days"],
            "source": effective["lead_time_source"],
            "is_missing": effective["lead_time_days"] is None,
            "is_fallback": effective["lead_time_source"] in {"business_default", "configured_default"},
            "blocks_forecast": False,
            "warning": "Missing supplier lead time." if effective["lead_time_days"] is None else None,
        },
        "current_stock": {
            "value": product.current_stock,
            "source": forecast.get("inventory_source") or "product_current_stock_cache",
            "is_missing": product.current_stock is None,
            "is_fallback": False,
            "blocks_forecast": product.current_stock is None,
        },
        "demand_history": {
            "value": has_demand_history,
            "source": forecast.get("demand_source") or "none",
            "is_missing": not has_demand_history,
            "is_fallback": forecast.get("demand_source") == "usage_history",
            "blocks_forecast": False,
            "warning": "No shipped demand history; product may be monitor-only." if not has_demand_history else None,
        },
        "cost": {
            "value": effective["cost_price"],
            "source": effective["cost_source"],
            "is_missing": effective["cost_price"] is None,
            "is_fallback": effective["cost_source"] in {"orderpro_purchase_order_line", "local_purchase_order_line"},
            "blocks_forecast": False,
        },
        "pack_size": {
            "value": effective["pack_size"],
            "source": effective["pack_size_source"],
            "is_missing": effective["pack_size"] is None,
            "is_fallback": False,
            "blocks_forecast": False,
            "warning": "Pack size is missing; no order multiple is applied." if effective["pack_size"] is None else None,
        },
        "seasonality": {
            "value": _seasonality_status(product),
            "source": "product_seasonality_profile" if product.seasonality_profile else "missing",
            "is_missing": product.seasonality_profile is None,
            "is_fallback": False,
            "blocks_forecast": False,
        },
    }


def _readiness_explanation(
    status: str,
    missing_inputs: list[str],
    warnings: list[str],
    recommendation_status: str | None,
) -> str:
    if status == "blocked":
        return f"Blocked because {', '.join(missing_inputs) or 'critical forecast inputs'} are missing."
    if status == "monitor_only":
        return "Monitor only: no usable demand history or open reorder signal is available."
    if status == "partially_ready":
        return f"Partially ready: recommendation can run, but {', '.join(warnings) or 'important inputs'} need review."
    return f"Ready: inputs support a {recommendation_status or 'forecast'} recommendation."


def _filter_readiness_rows(
    rows: list[dict[str, Any]],
    *,
    search: str | None,
    status: str | None,
    missing_input: str | None,
    has_open_demand: bool | None,
    has_stock: bool | None,
) -> list[dict[str, Any]]:
    filtered = rows
    filtered = filter_product_rows_by_search(
        filtered,
        search,
        exact_fields=("sku", "orderpro_sku", "barcode"),
        partial_fields=("product_name", "description"),
        supplier_fields=("supplier_name", "supplier_code"),
    )
    if status and status != "all":
        filtered = [row for row in filtered if row["readiness_status"] == status]
    if missing_input and missing_input != "all":
        filtered = [row for row in filtered if missing_input in row["missing_inputs"] or missing_input in row["warnings"]]
    if has_open_demand is not None:
        filtered = [row for row in filtered if (row["open_customer_demand"] > 0) is has_open_demand]
    if has_stock is not None:
        filtered = [row for row in filtered if ((row["current_stock"] or 0) > 0) is has_stock]
    return filtered


def _sort_readiness_rows(rows: list[dict[str, Any]], *, sort_by: str, sort_direction: str) -> list[dict[str, Any]]:
    reverse = sort_direction.lower() == "desc"
    key_map = {
        "readiness_score": lambda row: (row["readiness_score"], row["product_id"]),
        "status": lambda row: (row["readiness_status"], row["product_id"]),
        "sku": lambda row: (row["sku"] or "", row["product_id"]),
        "product_name": lambda row: (row["product_name"] or "", row["product_id"]),
        "stock": lambda row: (row["current_stock"] or 0, row["product_id"]),
        "open_demand": lambda row: (row["open_customer_demand"], row["product_id"]),
        "recommended_quantity": lambda row: (row["recommended_quantity"] or 0, row["product_id"]),
    }
    return sorted(rows, key=key_map.get(sort_by, key_map["readiness_score"]), reverse=reverse)


def safe_csv_text(value: Any) -> Any:
    if value is None:
        return ""
    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


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
    effective = effective_forecast_inputs(db, product)
    profile = product.forecast_input_profile
    if profile is None:
        return effective

    merged = dict(effective)
    if merged["cost_price"] is None and positive(profile.cost_price) is not None:
        merged["cost_price"] = positive(profile.cost_price)
        merged["cost_source"] = profile.cost_source
        merged["cost_confidence"] = profile.cost_confidence
        merged["cost_updated_at"] = profile.cost_updated_at

    if merged["lead_time_days"] is None and profile.lead_time_days is not None:
        merged["lead_time_days"] = profile.lead_time_days
        merged["lead_time_source"] = profile.lead_time_source
        merged["lead_time_confidence"] = profile.lead_time_confidence

    if merged["moq_source"] in {"business_default", "missing"} and positive(profile.min_order_qty) is not None:
        merged["min_order_qty"] = positive(profile.min_order_qty)
        merged["moq_source"] = profile.moq_source

    if merged["pack_size"] is None and positive(profile.pack_size) is not None:
        merged["pack_size"] = positive(profile.pack_size)
        merged["pack_size_source"] = profile.pack_size_source

    if merged["safety_stock_source"] == "business_default" and profile.safety_stock is not None:
        merged["safety_stock"] = profile.safety_stock
        merged["safety_stock_source"] = profile.safety_stock_source

    return refresh_input_status(product, merged)


def refresh_input_status(product: Product, inputs: dict[str, Any]) -> dict[str, Any]:
    blocking = []
    warnings = []
    if product.supplier_id is None:
        blocking.append("missing_supplier")
    if inputs["lead_time_days"] is None:
        warnings.append("missing_lead_time")
    if inputs["cost_price"] is None:
        warnings.append("missing_cost")
    if inputs["pack_size"] is None:
        warnings.append("missing_pack_size")
    if inputs["moq_source"] == "business_default":
        warnings.append("fallback_moq")
    if inputs["lead_time_source"] == "configured_default":
        warnings.append("fallback_lead_time")

    available_inputs = []
    missing_inputs = []
    for name, present in {
        "supplier_id": product.supplier_id is not None,
        "supplier_sku": bool(product.supplier_sku),
        "cost_price": inputs["cost_price"] is not None,
        "lead_time": inputs["lead_time_days"] is not None,
        "moq": inputs["min_order_qty"] is not None,
        "pack_size": inputs["pack_size"] is not None,
        "safety_stock": inputs["safety_stock"] is not None,
        "current_stock": product.current_stock is not None,
    }.items():
        (available_inputs if present else missing_inputs).append(name)

    refreshed = dict(inputs)
    refreshed["blocking_issues"] = blocking
    refreshed["warning_issues"] = warnings
    refreshed["available_inputs"] = sorted(available_inputs)
    refreshed["missing_inputs"] = sorted(missing_inputs)
    refreshed["readiness_score"] = round(
        (len(available_inputs) / (len(available_inputs) + len(missing_inputs))) * 100,
        2,
    )
    return refreshed
