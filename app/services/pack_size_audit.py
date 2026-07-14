from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models.product import Product
from app.models.product_forecast_input_profile import ProductForecastInputProfile
from app.models.product_master_item import ProductMasterItem
from app.models.product_supplier import ProductSupplier
from app.models.purchase_order import PurchaseOrderLine
from app.models.recommendation import Recommendation
from app.services.forecast_input_reconciliation import profile_or_effective_inputs
from app.services.forecasting import round_order_quantity
from app.services.recommendation_audit import (
    explain_product_recommendation,
    purchase_readiness_for_product,
)


TRUSTED_MAPPING_STATUSES = {"matched", "confirmed"}
MAX_REASONABLE_PACK_SIZE = 1000.0


def pack_size_audit(db: Session, *, sample_limit: int = 25) -> dict[str, Any]:
    products = (
        db.query(Product)
        .options(
            selectinload(Product.supplier_record),
            selectinload(Product.product_suppliers).selectinload(ProductSupplier.supplier),
            selectinload(Product.forecast_input_profile),
            selectinload(Product.inventory_positions),
        )
        .order_by(Product.id.asc())
        .all()
    )
    recommendations_by_product = {
        product_id
        for (product_id,) in db.query(Recommendation.product_id).distinct().all()
        if product_id is not None
    }

    safe_candidates = []
    conflicts = []
    no_candidate_count = 0
    missing_effective_count = 0
    legacy_pack_product_count = 0
    clear_legacy_candidate_count = 0
    blocked_only_missing_pack = 0
    top_supplier_counter: Counter[str] = Counter()
    top_product_rows = []
    impact_rows = []
    impact_summary = Counter()

    for product in products:
        effective = profile_or_effective_inputs(db, product)
        has_effective_pack_size = positive(effective.get("pack_size")) is not None
        if not has_effective_pack_size:
            missing_effective_count += 1
            supplier_label = product.supplier_record.name if product.supplier_record else "Missing supplier"
            top_supplier_counter[supplier_label] += 1
            if len(top_product_rows) < sample_limit:
                top_product_rows.append(product_sample(product, effective))

        candidates = legacy_pack_candidates(product)
        if candidates:
            legacy_pack_product_count += 1
        candidate_result = classify_pack_size_candidate(product, effective, candidates)

        if candidate_result["status"] == "safe":
            clear_legacy_candidate_count += 1
            safe_candidates.append(candidate_result["candidate"])
            impact = recommendation_impact_simulation(db, product, candidate_result["candidate"])
            if impact is not None:
                impact_rows.append(impact)
                impact_summary["products_simulated"] += 1
                impact_summary["would_become_order_ready"] += int(impact["would_become_order_ready"])
                impact_summary["quantity_would_change"] += int(impact["current_recommended_quantity"] != impact["simulated_recommended_quantity"])
                impact_summary["stale_demand_still_needs_review"] += int(impact["stale_demand_still_needs_review"])
                impact_summary["missing_cost_still_needs_review"] += int(impact["missing_cost_still_needs_review"])
        elif candidate_result["status"] == "conflict":
            conflicts.append(candidate_result["conflict"])
        elif not has_effective_pack_size:
            no_candidate_count += 1

        if not has_effective_pack_size and product.id in recommendations_by_product:
            explanation = explain_product_recommendation(db, product.id)
            if explanation and only_missing_pack_blocks_purchase_readiness(explanation):
                blocked_only_missing_pack += 1

    source_counts = pack_size_source_counts(db, total_products=len(products))
    safe_candidate_count = len(safe_candidates)
    conflict_count = len(conflicts)

    return {
        "summary": {
            "total_products": len(products),
            "products_missing_effective_pack_size": missing_effective_count,
            "products_with_existing_profile_pack_size": source_counts["product_forecast_input_profiles"]["populated"],
            "products_with_legacy_product_supplier_pack_size": legacy_pack_product_count,
            "products_with_one_clear_legacy_pack_size_candidate": clear_legacy_candidate_count,
            "safe_candidate_count": safe_candidate_count,
            "conflict_count": conflict_count,
            "no_candidate_count": no_candidate_count,
            "products_with_recommendations_blocked_or_review_only_because_missing_pack_size": blocked_only_missing_pack,
        },
        "source_counts": source_counts,
        "top_suppliers_affected": [
            {"supplier_name": supplier_name, "missing_pack_size_products": count}
            for supplier_name, count in top_supplier_counter.most_common(10)
        ],
        "top_products_affected": top_product_rows[:sample_limit],
        "safe_candidates": safe_candidates[:sample_limit],
        "conflicts": conflicts[:sample_limit],
        "recommendation_impact_simulation": {
            "summary": {
                "products_simulated": impact_summary["products_simulated"],
                "would_become_order_ready": impact_summary["would_become_order_ready"],
                "quantity_would_change": impact_summary["quantity_would_change"],
                "stale_demand_still_needs_review": impact_summary["stale_demand_still_needs_review"],
                "missing_cost_still_needs_review": impact_summary["missing_cost_still_needs_review"],
            },
            "items": impact_rows[:sample_limit],
        },
        "rules": {
            "trusted_mapping_statuses": sorted(TRUSTED_MAPPING_STATUSES),
            "max_reasonable_pack_size": MAX_REASONABLE_PACK_SIZE,
            "apply_changes": False,
        },
    }


def pack_size_source_counts(db: Session, *, total_products: int) -> dict[str, Any]:
    profile_populated = (
        db.query(func.count(ProductForecastInputProfile.id))
        .filter(ProductForecastInputProfile.pack_size.is_not(None))
        .filter(ProductForecastInputProfile.pack_size > 0)
        .scalar()
        or 0
    )
    profile_rows = db.query(func.count(ProductForecastInputProfile.id)).scalar() or 0
    supplier_populated = (
        db.query(func.count(ProductSupplier.id))
        .filter(ProductSupplier.pack_size.is_not(None))
        .filter(ProductSupplier.pack_size > 0)
        .scalar()
        or 0
    )
    supplier_rows = db.query(func.count(ProductSupplier.id)).scalar() or 0
    po_line_populated = (
        db.query(func.count(PurchaseOrderLine.id))
        .filter(PurchaseOrderLine.pack_size.is_not(None))
        .filter(PurchaseOrderLine.pack_size > 0)
        .scalar()
        or 0
    )
    po_line_rows = db.query(func.count(PurchaseOrderLine.id)).scalar() or 0
    master_item_rows = db.query(func.count(ProductMasterItem.id)).scalar() or 0
    product_with_pack_attr = hasattr(Product, "pack_size")

    return {
        "product_forecast_input_profiles": {
            "field": "pack_size",
            "populated": int(profile_populated),
            "missing_or_non_positive": int(max(profile_rows - profile_populated, 0)),
            "products_without_profile": int(max(total_products - profile_rows, 0)),
            "trusted": True,
            "legacy_evidence_only": False,
            "recommended_use": "Current effective pack-size source.",
        },
        "product_suppliers": {
            "field": "pack_size",
            "populated": int(supplier_populated),
            "missing_or_non_positive": int(max(supplier_rows - supplier_populated, 0)),
            "trusted": False,
            "legacy_evidence_only": True,
            "recommended_use": "Candidate evidence only when trusted, unique, and supplier-matched.",
        },
        "product_master_items": {
            "field": None,
            "populated": 0,
            "missing_or_non_positive": int(master_item_rows),
            "trusted": False,
            "legacy_evidence_only": True,
            "recommended_use": "No pack-size field available.",
        },
        "products": {
            "field": "pack_size" if product_with_pack_attr else None,
            "populated": 0,
            "missing_or_non_positive": int(total_products),
            "trusted": False,
            "legacy_evidence_only": False,
            "recommended_use": "No direct Product.pack_size column in current model.",
        },
        "purchase_order_lines": {
            "field": "pack_size",
            "populated": int(po_line_populated),
            "missing_or_non_positive": int(max(po_line_rows - po_line_populated, 0)),
            "trusted": False,
            "legacy_evidence_only": True,
            "recommended_use": "Historical PO snapshot evidence, not an automatic product default.",
        },
    }


def legacy_pack_candidates(product: Product) -> list[dict[str, Any]]:
    candidates = []
    for mapping in product.product_suppliers:
        pack_size = positive(mapping.pack_size)
        if pack_size is None:
            continue
        candidates.append(
            {
                "product_supplier_id": mapping.id,
                "product_id": product.id,
                "supplier_id": mapping.supplier_id,
                "supplier_name": mapping.supplier.name if mapping.supplier else None,
                "pack_size": pack_size,
                "match_status": mapping.match_status,
                "match_method": mapping.match_method,
                "is_preferred": bool(mapping.is_preferred),
                "supplier_matches_canonical": product.supplier_id is not None and mapping.supplier_id == product.supplier_id,
                "trusted_mapping": mapping.match_status in TRUSTED_MAPPING_STATUSES,
                "reasonable": pack_size <= MAX_REASONABLE_PACK_SIZE,
            }
        )
    return candidates


def classify_pack_size_candidate(
    product: Product,
    effective_inputs: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    if positive(effective_inputs.get("pack_size")) is not None:
        return {"status": "already_has_effective_pack_size"}
    if not candidates:
        return {"status": "no_candidate"}

    matching_trusted = [
        candidate
        for candidate in candidates
        if candidate["trusted_mapping"]
        and candidate["supplier_matches_canonical"]
        and candidate["reasonable"]
        and product.supplier_id is not None
    ]
    unique_sizes = sorted({candidate["pack_size"] for candidate in matching_trusted})
    all_unique_sizes = sorted({candidate["pack_size"] for candidate in candidates})

    if len(unique_sizes) == 1 and len(matching_trusted) == 1 and len(candidates) == 1:
        candidate = dict(matching_trusted[0])
        candidate.update(
            {
                "product_name": product.name,
                "canonical_supplier_id": product.supplier_id,
                "canonical_supplier_name": product.supplier_record.name if product.supplier_record else None,
                "candidate_count": len(matching_trusted),
            }
        )
        return {"status": "safe", "candidate": candidate}

    if len(unique_sizes) > 1 or len(all_unique_sizes) > 1:
        return {
            "status": "conflict",
            "conflict": {
                "product_id": product.id,
                "product_name": product.name,
                "canonical_supplier_id": product.supplier_id,
                "canonical_supplier_name": product.supplier_record.name if product.supplier_record else None,
                "candidate_pack_sizes": all_unique_sizes,
                "trusted_supplier_matched_pack_sizes": unique_sizes,
                "candidates": candidates,
            },
        }

    return {"status": "no_candidate"}


def recommendation_impact_simulation(
    db: Session,
    product: Product,
    candidate: dict[str, Any],
) -> dict[str, Any] | None:
    explanation = explain_product_recommendation(db, product.id)
    if explanation is None:
        return None
    current_forecast = explanation["forecast_snapshot"]
    current_quantity = float(explanation.get("recommended_quantity") or 0)
    simulated_forecast = dict(current_forecast)
    simulated_inputs = profile_or_effective_inputs(db, product)
    simulated_inputs = dict(simulated_inputs)
    simulated_inputs["pack_size"] = candidate["pack_size"]
    simulated_inputs["pack_size_source"] = "legacy_product_supplier_backfill_candidate"
    simulated_inputs["warning_issues"] = [
        issue for issue in simulated_inputs.get("warning_issues", []) if issue != "missing_pack_size"
    ]
    simulated_quantity = simulated_recommended_quantity(product, simulated_forecast, simulated_inputs)
    simulated_forecast["recommended_qty"] = simulated_quantity
    simulated_forecast["pack_size"] = candidate["pack_size"]
    simulated_forecast["pack_size_source"] = "legacy_product_supplier_backfill_candidate"

    simulated_warnings = [
        warning for warning in explanation.get("warnings", []) if not warning.startswith("Missing pack size")
    ]
    simulated_readiness = purchase_readiness_for_product(
        status=explanation["status"],
        blockers=explanation["blockers"],
        warnings=simulated_warnings,
        effective_inputs=simulated_inputs,
        forecast=simulated_forecast,
        recommended_quantity=simulated_quantity,
    )
    current_readiness = explanation["purchase_readiness_status"]
    simulated_status = simulated_readiness["status"]
    return {
        "product_id": product.id,
        "product_name": product.name,
        "candidate_pack_size": candidate["pack_size"],
        "current_purchase_readiness": current_readiness,
        "simulated_purchase_readiness": simulated_status,
        "current_recommended_quantity": current_quantity,
        "simulated_recommended_quantity": simulated_quantity,
        "would_become_order_ready": current_readiness != "order_ready" and simulated_status == "order_ready",
        "stale_demand_still_needs_review": bool(explanation.get("stale_demand_only")) and simulated_status != "order_ready",
        "missing_cost_still_needs_review": "Missing cost" in explanation.get("warnings", []) and simulated_status != "order_ready",
        "simulated_issues": simulated_readiness["issues"],
    }


def simulated_recommended_quantity(
    product: Product,
    forecast: dict[str, Any],
    effective_inputs: dict[str, Any],
) -> float:
    if forecast.get("recommended_action") != "reorder":
        return 0.0
    raw_quantity = max(
        float(forecast.get("total_required_stock") or 0)
        - float(forecast.get("current_stock") or 0)
        - float(forecast.get("incoming_qty") or 0),
        0.0,
    )
    if raw_quantity <= 0:
        return 0.0
    minimum_order_quantity = positive(effective_inputs.get("min_order_qty")) or 0.0
    return round_order_quantity(
        max(raw_quantity, minimum_order_quantity, 0.0),
        product,
        pack_size=positive(effective_inputs.get("pack_size")),
    )


def only_missing_pack_blocks_purchase_readiness(explanation: dict[str, Any]) -> bool:
    if explanation.get("purchase_readiness_status") == "order_ready":
        return False
    issues = set(explanation.get("purchase_readiness_issues") or [])
    return bool(issues) and issues.issubset({"Missing pack size"})


def positive(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def product_sample(product: Product, effective_inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": product.id,
        "product_name": product.name,
        "supplier_id": product.supplier_id,
        "supplier_name": product.supplier_record.name if product.supplier_record else None,
        "current_pack_size": effective_inputs.get("pack_size"),
        "pack_size_source": effective_inputs.get("pack_size_source"),
    }
