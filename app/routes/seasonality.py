from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.product import Product
from app.models.product_historical_link import ProductHistoricalLink
from app.models.product_seasonality_profile import ProductSeasonalityProfile
from app.schemas.seasonality import (
    ProductSeasonalityProfileResponse,
    SeasonalProductResponse,
    SeasonalitySummaryResponse,
)
from app.services.seasonality import interpret_current_seasonality, normalize_month
from app.services.historical_product_reconciliation import (
    build_reconciliation_plan,
    confirmed_links_for_products,
)
from app.services.seasonality import collect_contributing_usage_rows
from app.services.perf_logging import perf_timer
from app.services.product_search import filter_product_rows_by_search


router = APIRouter(tags=["seasonality"])

CONFIDENCE_ORDER = {
    "insufficient": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}


def _orderpro_product_filter():
    return (
        (Product.source_system == "orderpro")
        | (Product.orderpro_id.is_not(None))
        | (Product.orderpro_sku.is_not(None))
    )


def _profile_to_product_response(product: Product, month: int) -> SeasonalProductResponse:
    profile = product.seasonality_profile
    interpretation = interpret_current_seasonality(profile, month=month)
    supplier = product.supplier_record

    return SeasonalProductResponse(
        product_id=product.id,
        orderpro_sku=product.orderpro_sku,
        name=product.name,
        supplier_id=product.supplier_id,
        supplier_name=supplier.name if supplier else None,
        current_stock=float(product.current_stock or 0),
        seasonality_tag=profile.seasonality_tag if profile else product.seasonality_tag,
        current_seasonality_status=interpretation["current_status"],
        selected_month=month,
        selected_month_units=interpretation["selected_month_units"],
        selected_month_index=interpretation["selected_month_index"],
        peak_months=profile.peak_months if profile else [],
        primary_season=profile.primary_season if profile else None,
        seasonality_strength=profile.seasonality_strength if profile else None,
        confidence_score=profile.confidence_score if profile else None,
        confidence_label=profile.confidence_label if profile else None,
        history_start=profile.history_start if profile else None,
        history_end=profile.history_end if profile else None,
        years_covered=profile.years_covered if profile else None,
    )


def _profile_detail_response(
    db: Session,
    product: Product,
    month: int,
) -> ProductSeasonalityProfileResponse:
    profile = product.seasonality_profile
    if profile is None:
        raise HTTPException(status_code=404, detail="Seasonality profile not found for product.")
    interpretation = interpret_current_seasonality(profile, month=month)
    confirmed_links = confirmed_links_for_products(db, [product.id])
    _, contribution = collect_contributing_usage_rows(db, product, confirmed_links)

    return ProductSeasonalityProfileResponse(
        product_id=product.id,
        orderpro_sku=product.orderpro_sku,
        name=product.name,
        history_start=profile.history_start,
        history_end=profile.history_end,
        history_months=profile.history_months,
        active_months=profile.active_months,
        years_covered=profile.years_covered,
        total_units=profile.total_units,
        average_monthly_units=profile.average_monthly_units,
        monthly_units=profile.monthly_units,
        monthly_indices=profile.monthly_indices,
        peak_months=profile.peak_months or [],
        low_months=profile.low_months or [],
        primary_season=profile.primary_season,
        seasonality_tag=profile.seasonality_tag,
        seasonality_strength=profile.seasonality_strength,
        confidence_score=profile.confidence_score,
        confidence_label=profile.confidence_label,
        coefficient_of_variation=profile.coefficient_of_variation,
        calculation_version=profile.calculation_version,
        calculated_at=profile.calculated_at,
        current_interpretation=interpretation,
        direct_history_row_count=contribution["direct_history_row_count"],
        linked_history_row_count=contribution["linked_history_row_count"],
        contributing_historical_product_ids=contribution["contributing_historical_product_ids"],
        reconciliation_methods=contribution["reconciliation_methods"],
    )


@router.get("/seasonality/summary", response_model=SeasonalitySummaryResponse)
def get_seasonality_summary(
    month: int | None = Query(default=None, ge=1, le=12),
    include_legacy: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    selected_month = normalize_month(month)
    with perf_timer("seasonality.summary", month=selected_month, include_legacy=include_legacy, summary_calculated=True) as perf:
        products = (
            db.query(Product)
            .options(joinedload(Product.seasonality_profile))
        )
        if not include_legacy:
            products = products.filter(_orderpro_product_filter())
        products = products.all()
        profiles = [product.seasonality_profile for product in products if product.seasonality_profile is not None]
        current_status_counts = Counter(
            interpret_current_seasonality(profile, month=selected_month)["current_status"]
            for profile in profiles
        )
        missing_profile_count = len(products) - len(profiles)
        if missing_profile_count:
            current_status_counts["insufficient_data"] += missing_profile_count

        perf["product_count"] = len(products)
        return SeasonalitySummaryResponse(
            classification_counts=dict(Counter(profile.seasonality_tag for profile in profiles)),
            confidence_counts=dict(Counter(profile.confidence_label for profile in profiles)),
            current_season_counts=dict(current_status_counts),
            profile_count=len(profiles),
            product_count=len(products),
            missing_profile_count=missing_profile_count,
            selected_month=selected_month,
            include_legacy=include_legacy,
        )


@router.get("/products/seasonal", response_model=list[SeasonalProductResponse])
def list_seasonal_products(
    month: int | None = Query(default=None, ge=1, le=12),
    status: str | None = Query(default=None),
    seasonality_tag: str | None = Query(default=None),
    supplier_id: int | None = Query(default=None),
    min_confidence: str | None = Query(default=None),
    search: str | None = Query(default=None),
    active_only: bool = Query(default=True),
    include_legacy: bool = Query(default=False),
    sort_by: str = Query(default="seasonal_index"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    selected_month = normalize_month(month)
    with perf_timer(
        "seasonality.products",
        month=selected_month,
        status=status,
        seasonality_tag=seasonality_tag,
        supplier_id=supplier_id,
        min_confidence=min_confidence,
        search=search,
        active_only=active_only,
        include_legacy=include_legacy,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    ) as perf:
        query = db.query(Product).options(
            joinedload(Product.seasonality_profile),
            joinedload(Product.supplier_record),
        )
        if active_only:
            query = query.filter(Product.is_active.is_(True))
        if not include_legacy:
            query = query.filter(_orderpro_product_filter())
        if supplier_id is not None:
            query = query.filter(Product.supplier_id == supplier_id)

        products = query.all()
        rows = [_profile_to_product_response(product, selected_month) for product in products]

        if search:
            matched_ids = {
                row["product_id"]
                for row in filter_product_rows_by_search(
                    [seasonal_row.model_dump() for seasonal_row in rows],
                    search,
                    exact_fields=("orderpro_sku",),
                    partial_fields=("name",),
                    supplier_fields=("supplier_name",),
                )
            }
            rows = [row for row in rows if row.product_id in matched_ids]

        if status:
            rows = [row for row in rows if row.current_seasonality_status == status]
        if seasonality_tag:
            rows = [row for row in rows if row.seasonality_tag == seasonality_tag]
        if min_confidence:
            minimum = CONFIDENCE_ORDER.get(min_confidence)
            if minimum is None:
                raise HTTPException(status_code=400, detail="Invalid min_confidence value.")
            rows = [
                row
                for row in rows
                if CONFIDENCE_ORDER.get(row.confidence_label or "insufficient", 0) >= minimum
            ]

        if sort_by == "seasonal_index":
            rows.sort(key=lambda row: (row.selected_month_index or 0, row.name.lower()), reverse=True)
        elif sort_by == "current_stock":
            rows.sort(key=lambda row: row.current_stock)
        elif sort_by == "product_name":
            rows.sort(key=lambda row: row.name.lower())
        elif sort_by == "recommended_qty":
            rows.sort(key=lambda row: (row.selected_month_index or 0, row.current_stock), reverse=True)
        else:
            raise HTTPException(status_code=400, detail="Invalid sort_by value.")

        perf["total"] = len(rows)
        result = rows[offset : offset + limit]
        perf["returned"] = len(result)
        return result


@router.get("/products/{product_id}/seasonality", response_model=ProductSeasonalityProfileResponse)
def get_product_seasonality(
    product_id: int,
    month: int | None = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
):
    product = (
        db.query(Product)
        .options(joinedload(Product.seasonality_profile))
        .filter(Product.id == product_id)
        .first()
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return _profile_detail_response(db, product, normalize_month(month))


@router.get("/historical-product-links/summary")
def get_historical_product_link_summary(
    include_name_suggestions: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    plan = build_reconciliation_plan(db, include_name_suggestions=include_name_suggestions)
    return {
        "summary": plan.summary,
        "warnings": plan.warnings,
    }


@router.get("/historical-product-links/review")
def list_historical_product_link_review(
    include_name_suggestions: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    plan = build_reconciliation_plan(db, include_name_suggestions=include_name_suggestions)
    review_rows = plan.ambiguous_matches + plan.name_suggestions
    existing_review_links = (
        db.query(ProductHistoricalLink)
        .filter(ProductHistoricalLink.status == "needs_review")
        .limit(limit)
        .all()
    )
    existing_rows = [
        {
            "orderpro_product_id": link.orderpro_product_id,
            "historical_product_id": link.historical_product_id,
            "match_method": link.match_method,
            "match_value": link.match_value,
            "confidence_label": link.confidence_label,
            "status": link.status,
        }
        for link in existing_review_links
    ]
    return {
        "review_count": len(review_rows) + len(existing_rows),
        "review_rows": (review_rows + existing_rows)[:limit],
    }
