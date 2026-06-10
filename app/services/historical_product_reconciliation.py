from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product_historical_link import ProductHistoricalLink
from app.models.usage_history import UsageHistory
from app.services.seasonality import utc_now


SAFE_LINK_STATUSES = {"auto_confirmed", "manually_confirmed"}
REVIEW_LINK_STATUSES = {"needs_review"}
EXCLUDED_LINK_STATUSES = {"needs_review", "rejected"}
PLACEHOLDER_BARCODES = {
    "",
    "0",
    "00",
    "000",
    "0000",
    "00000",
    "000000",
    "0000000",
    "00000000",
    "000000000000",
    "0000000000000",
    "NA",
    "N/A",
    "NONE",
    "NULL",
    "UNKNOWN",
    "NO",
    "NOBARCODE",
    "NOBC",
    "NOTAPPLICABLE",
}


@dataclass
class ReconciliationPlan:
    summary: dict[str, Any]
    safe_matches: list[dict[str, Any]]
    ambiguous_matches: list[dict[str, Any]]
    name_suggestions: list[dict[str, Any]]
    warnings: list[str]


def is_orderpro_product(product: Product) -> bool:
    return bool(product.source_system == "orderpro" or product.orderpro_id or product.orderpro_sku)


def normalize_barcode(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\xa0", " ").strip().upper()
    text = re.sub(r"\s+", "", text)
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".")[0]
    text = re.sub(r"[^A-Z0-9]+", "", text)
    if text in PLACEHOLDER_BARCODES:
        return None
    return text or None


def normalize_name(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"[^A-Z0-9]+", "", str(value).upper())
    return text or None


def _product_summary(product: Product) -> dict[str, Any]:
    return {
        "id": product.id,
        "name": product.name,
        "barcode": product.barcode,
        "orderpro_sku": product.orderpro_sku,
        "source_system": product.source_system,
    }


def _usage_stats_by_product(db: Session) -> tuple[dict[int, int], dict[int, float]]:
    rows = (
        db.query(
            UsageHistory.product_id,
            func.count(UsageHistory.id),
            func.coalesce(func.sum(UsageHistory.net_qty), 0),
        )
        .group_by(UsageHistory.product_id)
        .all()
    )
    return {row[0]: int(row[1]) for row in rows}, {row[0]: float(row[2] or 0) for row in rows}


def _group_by_barcode(products: list[Product]) -> tuple[dict[str, list[Product]], list[Product]]:
    groups: dict[str, list[Product]] = defaultdict(list)
    invalid: list[Product] = []
    for product in products:
        barcode = normalize_barcode(product.barcode)
        if barcode:
            groups[barcode].append(product)
        else:
            invalid.append(product)
    return groups, invalid


def build_reconciliation_plan(
    db: Session,
    *,
    product_id: int | None = None,
    include_name_suggestions: bool = False,
    match_version: str = "historical-link-v1",
) -> ReconciliationPlan:
    del match_version
    usage_row_counts, usage_quantities = _usage_stats_by_product(db)
    products = db.query(Product).order_by(Product.id.asc()).all()
    orderpro_products = [product for product in products if is_orderpro_product(product)]
    historical_products = [
        product
        for product in products
        if product.id in usage_row_counts and not is_orderpro_product(product)
    ]
    if product_id is not None:
        orderpro_products = [product for product in orderpro_products if product.id == product_id]

    orderpro_by_barcode, invalid_orderpro = _group_by_barcode(orderpro_products)
    historical_by_barcode, invalid_historical = _group_by_barcode(historical_products)
    duplicate_orderpro_barcode_groups = {
        barcode: group for barcode, group in orderpro_by_barcode.items() if len(group) > 1
    }
    duplicate_historical_barcode_groups = {
        barcode: group for barcode, group in historical_by_barcode.items() if len(group) > 1
    }

    existing_links = {
        (link.orderpro_product_id, link.historical_product_id): link
        for link in db.query(ProductHistoricalLink).all()
    }
    linked_historical_ids = {
        link.historical_product_id
        for link in existing_links.values()
        if link.status in SAFE_LINK_STATUSES
    }

    safe_matches: list[dict[str, Any]] = []
    ambiguous_matches: list[dict[str, Any]] = []
    matched_orderpro_ids: set[int] = set()
    matched_historical_ids: set[int] = set()

    for barcode, historical_group in historical_by_barcode.items():
        orderpro_group = orderpro_by_barcode.get(barcode, [])
        if len(orderpro_group) == 1:
            orderpro_product = orderpro_group[0]
            for historical_product in historical_group:
                safe_matches.append(
                    {
                        "orderpro_product_id": orderpro_product.id,
                        "historical_product_id": historical_product.id,
                        "match_method": "barcode_exact",
                        "match_value": barcode,
                        "confidence_score": 1.0,
                        "confidence_label": "high",
                        "status": "auto_confirmed",
                        "orderpro_product": _product_summary(orderpro_product),
                        "historical_product": _product_summary(historical_product),
                        "historical_usage_rows": usage_row_counts.get(historical_product.id, 0),
                        "historical_net_quantity": usage_quantities.get(historical_product.id, 0.0),
                    }
                )
                matched_orderpro_ids.add(orderpro_product.id)
                matched_historical_ids.add(historical_product.id)
        elif len(orderpro_group) > 1:
            ambiguous_matches.append(
                {
                    "reason": "duplicate_orderpro_barcode",
                    "match_value": barcode,
                    "orderpro_product_ids": [product.id for product in orderpro_group],
                    "historical_product_ids": [product.id for product in historical_group],
                }
            )

    name_suggestions: list[dict[str, Any]] = []
    if include_name_suggestions:
        orderpro_by_name: dict[str, list[Product]] = defaultdict(list)
        for product in orderpro_products:
            normalized = normalize_name(product.name)
            if normalized:
                orderpro_by_name[normalized].append(product)
        for historical_product in historical_products:
            if historical_product.id in matched_historical_ids:
                continue
            normalized = normalize_name(historical_product.name)
            candidates = orderpro_by_name.get(normalized or "", [])
            if len(candidates) == 1:
                name_suggestions.append(
                    {
                        "orderpro_product_id": candidates[0].id,
                        "historical_product_id": historical_product.id,
                        "match_method": "name_exact",
                        "match_value": normalized,
                        "confidence_score": 0.5,
                        "confidence_label": "low",
                        "status": "needs_review",
                    }
                )

    existing_auto_link_keys = {
        key
        for key, link in existing_links.items()
        if link.match_method == "barcode_exact" and link.status in SAFE_LINK_STATUSES
    }
    safe_keys = {(match["orderpro_product_id"], match["historical_product_id"]) for match in safe_matches}
    direct_history_orderpro_ids = {
        product.id for product in orderpro_products if usage_row_counts.get(product.id, 0) > 0
    }
    covered_historical_ids = {match["historical_product_id"] for match in safe_matches}
    rows_covered = sum(usage_row_counts.get(product_id, 0) for product_id in covered_historical_ids)
    quantity_covered = sum(usage_quantities.get(product_id, 0.0) for product_id in covered_historical_ids)

    summary = {
        "total_orderpro_products": len(orderpro_products),
        "total_historical_products": len(historical_products),
        "distinct_legacy_historical_products": len(historical_products),
        "distinct_orderpro_products": len(orderpro_products),
        "legacy_products_with_valid_barcodes": sum(len(group) for group in historical_by_barcode.values()),
        "orderpro_products_with_valid_barcodes": sum(len(group) for group in orderpro_by_barcode.values()),
        "unique_barcode_matches": len(safe_matches),
        "safely_matched_orderpro_products": len(matched_orderpro_ids),
        "safely_matched_historical_products": len(matched_historical_ids),
        "multiple_legacy_products_matching_one_orderpro_product": sum(
            1 for count in Counter(match["orderpro_product_id"] for match in safe_matches).values() if count > 1
        ),
        "one_legacy_product_matching_multiple_orderpro_products": 0,
        "duplicate_orderpro_barcode_groups": len(duplicate_orderpro_barcode_groups),
        "duplicate_legacy_barcode_groups": len(duplicate_historical_barcode_groups),
        "blank_invalid_placeholder_legacy_barcodes": len(invalid_historical),
        "blank_invalid_placeholder_orderpro_barcodes": len(invalid_orderpro),
        "unmatched_orderpro_products": len([product for product in orderpro_products if product.id not in matched_orderpro_ids]),
        "unmatched_historical_products": len([product for product in historical_products if product.id not in matched_historical_ids]),
        "historical_usage_rows_covered_by_safe_matches": rows_covered,
        "raw_historical_net_quantity_covered_by_safe_matches": round(quantity_covered, 4),
        "historical_net_quantity_covered_by_safe_matches": round(quantity_covered, 4),
        "orderpro_products_with_direct_history": len(direct_history_orderpro_ids),
        "confirmed_historical_links_existing": len(linked_historical_ids),
        "links_to_create": len([key for key in safe_keys if key not in existing_links]),
        "links_to_update": len([key for key in safe_keys if key in existing_links]),
        "exact_name_review_suggestions": len(name_suggestions),
        "sample_duplicate_legacy_barcode_groups": [
            {"barcode": barcode, "product_ids": [product.id for product in group]}
            for barcode, group in list(duplicate_historical_barcode_groups.items())[:10]
        ],
        "sample_duplicate_orderpro_barcode_groups": [
            {"barcode": barcode, "product_ids": [product.id for product in group]}
            for barcode, group in list(duplicate_orderpro_barcode_groups.items())[:10]
        ],
        "sample_unmatched_orderpro_products": [
            _product_summary(product) for product in orderpro_products if product.id not in matched_orderpro_ids
        ][:10],
        "sample_unmatched_historical_products": [
            _product_summary(product) for product in historical_products if product.id not in matched_historical_ids
        ][:10],
        "safe_link_keys_changed": len(safe_keys - existing_auto_link_keys),
    }
    warnings = []
    if duplicate_orderpro_barcode_groups:
        warnings.append("Some OrderPro barcodes are duplicated; those candidates are needs_review and not auto-linked.")
    if name_suggestions:
        warnings.append("Exact-name matches are review suggestions only and are not auto-confirmed.")

    return ReconciliationPlan(
        summary=summary,
        safe_matches=safe_matches,
        ambiguous_matches=ambiguous_matches,
        name_suggestions=name_suggestions,
        warnings=warnings,
    )


def apply_safe_historical_links(
    db: Session,
    *,
    confirm_safe_barcode_matches: bool,
    product_id: int | None = None,
    include_name_suggestions: bool = False,
) -> ReconciliationPlan:
    if not confirm_safe_barcode_matches:
        raise ValueError("--confirm-safe-barcode-matches is required with --apply.")

    plan = build_reconciliation_plan(
        db,
        product_id=product_id,
        include_name_suggestions=include_name_suggestions,
    )
    now = utc_now()
    existing_links = {
        (link.orderpro_product_id, link.historical_product_id): link
        for link in db.query(ProductHistoricalLink).all()
    }
    historical_to_orderpro: dict[int, set[int]] = defaultdict(set)
    for link in existing_links.values():
        if link.status != "rejected":
            historical_to_orderpro[link.historical_product_id].add(link.orderpro_product_id)

    for match in plan.safe_matches:
        key = (match["orderpro_product_id"], match["historical_product_id"])
        other_orderpro_ids = historical_to_orderpro[match["historical_product_id"]] - {match["orderpro_product_id"]}
        if other_orderpro_ids:
            continue

        link = existing_links.get(key)
        if link is None:
            link = ProductHistoricalLink(
                orderpro_product_id=match["orderpro_product_id"],
                historical_product_id=match["historical_product_id"],
                created_at=now,
            )
            db.add(link)

        link.match_method = match["match_method"]
        link.match_value = match["match_value"]
        link.confidence_score = match["confidence_score"]
        link.confidence_label = match["confidence_label"]
        link.status = "auto_confirmed"
        link.notes = "Auto-confirmed deterministic exact barcode match."
        link.updated_at = now
        if link.confirmed_at is None:
            link.confirmed_at = now
        if not link.confirmed_by:
            link.confirmed_by = "system"

    db.commit()
    return plan


def confirmed_links_for_products(db: Session, orderpro_product_ids: list[int]) -> list[ProductHistoricalLink]:
    if not orderpro_product_ids:
        return []
    return (
        db.query(ProductHistoricalLink)
        .filter(
            ProductHistoricalLink.orderpro_product_id.in_(orderpro_product_ids),
            ProductHistoricalLink.status.in_(SAFE_LINK_STATUSES),
        )
        .all()
    )
