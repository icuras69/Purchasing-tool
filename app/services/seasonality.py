from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import sqrt
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.product import Product
from app.models.product_historical_link import ProductHistoricalLink
from app.models.product_seasonality_profile import ProductSeasonalityProfile
from app.models.usage_history import UsageHistory


CALCULATION_VERSION = "seasonality-v1"
DEFAULT_MINIMUM_HISTORY_MONTHS = 12
DEFAULT_APPROACHING_MONTHS = 2

SEASON_MONTHS = {
    "winter": (12, 1, 2),
    "spring": (3, 4, 5),
    "summer": (6, 7, 8),
    "autumn": (9, 10, 11),
}

MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


@dataclass
class SeasonalityAudit:
    source_table: str
    date_column: str
    quantity_columns: list[str]
    product_identifier_columns: list[str]
    history_start: date | None
    history_end: date | None
    historical_rows: int
    matched_rows: int
    unmatched_raw_rows: int
    matched_product_count: int
    negative_quantity_rows: int
    month_count: int
    months_with_history: list[str]


@dataclass
class SeasonalityPlan:
    audit: SeasonalityAudit
    profiles: list[dict[str, Any]]
    profiles_to_create: int
    profiles_to_update: int
    classification_counts: dict[str, int]
    confidence_counts: dict[str, int]
    insufficient_data_count: int
    reconciliation_coverage: dict[str, Any]
    warnings: list[str]


REPORT_ONLY_PROFILE_FIELDS = {
    "product_id",
    "product_name",
    "orderpro_sku",
    "direct_history_row_count",
    "linked_history_row_count",
    "contributing_historical_product_ids",
    "reconciliation_methods",
    "raw_linked_net_quantity",
    "positive_linked_quantity",
    "negative_linked_quantity",
    "negative_linked_row_count",
    "monthly_raw_net_quantity",
    "linked_product_month_clamped_quantity",
    "target_product_month_clamped_quantity",
    "quantity_used_for_seasonality",
    "quantity_removed_by_target_month_clamp",
    "quantity_removed_by_cross_link_offset",
    "quantity_transform_breakdown",
    "target_product_month_breakdown",
    "linked_historical_product_month_breakdown",
    "total_negative_quantity_retained",
    "total_negative_quantity_discarded_or_clamped",
    "total_quantity_removed",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_month(month: int | None) -> int:
    if month is None:
        return datetime.now(timezone.utc).month
    if month < 1 or month > 12:
        raise ValueError("month must be between 1 and 12")
    return month


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _inclusive_month_count(start: date | None, end: date | None) -> int:
    if not start or not end:
        return 0
    return (end.year - start.year) * 12 + end.month - start.month + 1


def _coefficient_of_variation(values: list[float]) -> float | None:
    if not values:
        return None
    mean = sum(values) / len(values)
    if mean <= 0:
        return None
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return sqrt(variance) / mean


def _season_for_month(month: int) -> str:
    for season, months in SEASON_MONTHS.items():
        if month in months:
            return season
    return "unknown"


def _months_until(source_month: int, target_month: int) -> int:
    return (target_month - source_month) % 12


def _confidence_label(score: float, tag: str) -> str:
    if tag == "insufficient_data":
        return "insufficient"
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def _classify_profile(
    *,
    history_months: int,
    active_months: int,
    years_covered: int,
    total_units: float,
    monthly_units: dict[int, float],
    monthly_indices: dict[int, float],
    minimum_history_months: int,
) -> tuple[str, str | None, list[int], list[int], float, float, str, float | None]:
    observed_values = list(monthly_units.values())
    coefficient = _coefficient_of_variation(observed_values)
    if (
        history_months < minimum_history_months
        or active_months < 4
        or years_covered < 2
        or total_units <= 0
        or len(observed_values) < 4
    ):
        return "insufficient_data", None, [], [], 0.0, 0.0, "insufficient", coefficient

    peak_months = sorted(month for month, index in monthly_indices.items() if index >= 1.35)
    low_months = sorted(month for month, index in monthly_indices.items() if index <= 0.65)
    max_index = max(monthly_indices.values()) if monthly_indices else 0.0
    min_index = min(monthly_indices.values()) if monthly_indices else 0.0
    strength = round(max(max_index - 1.0, 0.0), 4)
    max_month_units = max(observed_values) if observed_values else 0.0
    max_month_share = max_month_units / total_units if total_units else 0.0

    season_scores = {
        season: sum(monthly_indices.get(month, 0.0) for month in months) / len(months)
        for season, months in SEASON_MONTHS.items()
    }
    primary_season, primary_score = max(season_scores.items(), key=lambda item: item[1])
    secondary_score = sorted(season_scores.values(), reverse=True)[1]
    elevated_seasons = [season for season, score in season_scores.items() if score >= 1.2]

    if coefficient is not None and coefficient < 0.35 and max_index < 1.5:
        tag = "year_round"
        primary_season = None
    elif len(elevated_seasons) >= 2 and primary_score - secondary_score < 0.25:
        tag = "multi_peak"
        primary_season = None
    elif peak_months and primary_score >= 1.2 and primary_score - secondary_score >= 0.15:
        tag = primary_season
    else:
        tag = "year_round"
        primary_season = None

    score = 0.0
    score += min(years_covered / 3, 1.0) * 0.35
    score += min(active_months / 18, 1.0) * 0.25
    score += min(total_units / 100, 1.0) * 0.20
    score += min(strength / 1.0, 1.0) * 0.20
    if max_month_share > 0.45:
        score *= 0.55
    if coefficient is not None and coefficient < 0.2 and tag != "year_round":
        score *= 0.7
    score = round(min(max(score, 0.0), 1.0), 4)

    return tag, primary_season, peak_months, low_months, strength, score, _confidence_label(score, tag), coefficient


def calculate_product_profile(
    product: Product,
    usage_rows: list[UsageHistory],
    *,
    minimum_history_months: int = DEFAULT_MINIMUM_HISTORY_MONTHS,
    calculation_version: str = CALCULATION_VERSION,
    calculated_at: datetime | None = None,
) -> dict[str, Any]:
    calculated_at = calculated_at or utc_now()
    valid_rows = [row for row in usage_rows if row.date is not None]
    history_start = min((row.date for row in valid_rows), default=None)
    history_end = max((row.date for row in valid_rows), default=None)
    history_months = _inclusive_month_count(history_start, history_end)
    years_covered = len({row.date.year for row in valid_rows}) if valid_rows else 0

    monthly_bucket_units: dict[tuple[int, int], float] = defaultdict(float)
    negative_quantity_rows = 0
    for row in valid_rows:
        quantity = float(row.net_qty if row.net_qty is not None else row.qty_used or 0)
        if quantity < 0:
            negative_quantity_rows += 1
        monthly_bucket_units[(row.date.year, row.date.month)] += quantity

    monthly_units: dict[int, float] = {}
    for month in range(1, 13):
        values = [
            max(units, 0.0)
            for (year, bucket_month), units in monthly_bucket_units.items()
            if bucket_month == month
        ]
        if values:
            monthly_units[month] = round(sum(values) / len(values), 4)

    active_months = sum(1 for units in monthly_bucket_units.values() if units > 0)
    total_units = round(sum(max(units, 0.0) for units in monthly_bucket_units.values()), 4)
    observed_values = list(monthly_units.values())
    average_monthly_units = round(sum(observed_values) / len(observed_values), 4) if observed_values else 0.0
    monthly_indices = {
        month: round(units / average_monthly_units, 4) if average_monthly_units > 0 else 0.0
        for month, units in monthly_units.items()
    }

    tag, primary_season, peak_months, low_months, strength, confidence_score, confidence_label, coefficient = _classify_profile(
        history_months=history_months,
        active_months=active_months,
        years_covered=years_covered,
        total_units=total_units,
        monthly_units=monthly_units,
        monthly_indices=monthly_indices,
        minimum_history_months=minimum_history_months,
    )

    warnings = []
    if negative_quantity_rows:
        warnings.append(f"{negative_quantity_rows} negative/return usage rows were netted into monthly demand.")
    if history_months < minimum_history_months:
        warnings.append("History coverage is shorter than the configured minimum.")

    return {
        "product_id": product.id,
        "history_start": history_start,
        "history_end": history_end,
        "history_months": history_months,
        "active_months": active_months,
        "years_covered": years_covered,
        "total_units": total_units,
        "average_monthly_units": average_monthly_units,
        "monthly_units": {str(month): units for month, units in sorted(monthly_units.items())},
        "monthly_indices": {str(month): index for month, index in sorted(monthly_indices.items())},
        "peak_months": peak_months,
        "low_months": low_months,
        "primary_season": primary_season,
        "seasonality_tag": tag,
        "seasonality_strength": strength,
        "confidence_score": confidence_score,
        "confidence_label": confidence_label,
        "coefficient_of_variation": round(coefficient, 4) if coefficient is not None else None,
        "calculation_version": calculation_version,
        "calculated_at": calculated_at,
        "warnings": warnings,
    }


def calculate_quantity_transform_metrics(
    usage_rows: list[UsageHistory],
    *,
    linked_product_ids: set[int] | None = None,
) -> dict[str, Any]:
    linked_product_ids = linked_product_ids or set()
    valid_rows = [row for row in usage_rows if row.date is not None]
    linked_rows = [row for row in valid_rows if row.product_id in linked_product_ids]

    def quantity_for(row: UsageHistory) -> float:
        return float(row.net_qty if row.net_qty is not None else row.qty_used or 0)

    raw_linked_net_quantity = round(sum(quantity_for(row) for row in linked_rows), 4)
    positive_linked_quantity = round(sum(max(quantity_for(row), 0.0) for row in linked_rows), 4)
    negative_linked_quantity = round(sum(min(quantity_for(row), 0.0) for row in linked_rows), 4)
    negative_linked_row_count = sum(1 for row in linked_rows if quantity_for(row) < 0)

    linked_product_months: dict[tuple[int, int, int], float] = defaultdict(float)
    target_product_months: dict[tuple[int, int], float] = defaultdict(float)
    linked_product_month_count_by_target_month: dict[tuple[int, int], int] = defaultdict(int)
    for row in valid_rows:
        quantity = quantity_for(row)
        target_key = (row.date.year, row.date.month)
        target_product_months[target_key] += quantity
        if row.product_id in linked_product_ids:
            linked_key = (row.product_id, row.date.year, row.date.month)
            if linked_key not in linked_product_months:
                linked_product_month_count_by_target_month[target_key] += 1
            linked_product_months[linked_key] += quantity

    monthly_raw_net_quantity = round(sum(target_product_months.values()), 4)
    linked_product_month_clamped_quantity = round(
        sum(max(quantity, 0.0) for quantity in linked_product_months.values()),
        4,
    )
    target_product_month_clamped_quantity = round(
        sum(max(quantity, 0.0) for quantity in target_product_months.values()),
        4,
    )
    quantity_used_for_seasonality = target_product_month_clamped_quantity
    quantity_removed_by_target_month_clamp = round(
        sum(min(quantity, 0.0) for quantity in target_product_months.values()),
        4,
    )
    quantity_removed_by_cross_link_offset = round(
        linked_product_month_clamped_quantity - target_product_month_clamped_quantity,
        4,
    )

    altered_months = []
    target_product_month_breakdown = []
    for (year, month), raw_quantity in sorted(target_product_months.items()):
        transformed_quantity = max(raw_quantity, 0.0)
        target_product_month_breakdown.append(
            {
                "calendar_month": f"{year:04d}-{month:02d}",
                "raw_net_quantity": round(raw_quantity, 4),
                "transformed_clamped_quantity": round(transformed_quantity, 4),
                "quantity_actually_included": round(transformed_quantity, 4),
                "quantity_removed": round(raw_quantity - transformed_quantity, 4),
                "linked_product_month_count": linked_product_month_count_by_target_month.get((year, month), 0),
            }
        )
        if round(raw_quantity, 4) != round(transformed_quantity, 4):
            altered_months.append(
                {
                    "calendar_month": f"{year:04d}-{month:02d}",
                    "raw_net_quantity": round(raw_quantity, 4),
                    "transformed_clamped_quantity": round(transformed_quantity, 4),
                    "quantity_actually_included": round(transformed_quantity, 4),
                    "quantity_removed": round(raw_quantity - transformed_quantity, 4),
                    "linked_product_month_count": linked_product_month_count_by_target_month.get((year, month), 0),
                }
            )

    linked_historical_product_month_breakdown = [
        {
            "historical_product_id": product_id,
            "calendar_month": f"{year:04d}-{month:02d}",
            "raw_net_quantity": round(raw_quantity, 4),
            "transformed_clamped_quantity": round(max(raw_quantity, 0.0), 4),
        }
        for (product_id, year, month), raw_quantity in sorted(linked_product_months.items())
    ]

    return {
        "raw_linked_net_quantity": raw_linked_net_quantity,
        "positive_linked_quantity": positive_linked_quantity,
        "negative_linked_quantity": negative_linked_quantity,
        "negative_linked_row_count": negative_linked_row_count,
        "monthly_raw_net_quantity": monthly_raw_net_quantity,
        "linked_product_month_clamped_quantity": linked_product_month_clamped_quantity,
        "target_product_month_clamped_quantity": target_product_month_clamped_quantity,
        "quantity_used_for_seasonality": quantity_used_for_seasonality,
        "quantity_removed_by_target_month_clamp": quantity_removed_by_target_month_clamp,
        "quantity_removed_by_cross_link_offset": quantity_removed_by_cross_link_offset,
        "total_negative_quantity_retained": round(
            negative_linked_quantity + abs(quantity_removed_by_target_month_clamp),
            4,
        ),
        "total_negative_quantity_retained_abs": round(
            abs(negative_linked_quantity) - abs(quantity_removed_by_target_month_clamp),
            4,
        ),
        "total_negative_quantity_discarded_or_clamped": round(abs(quantity_removed_by_target_month_clamp), 4),
        "total_quantity_removed": round(abs(quantity_removed_by_target_month_clamp), 4),
        "quantity_transform_breakdown": altered_months,
        "target_product_month_breakdown": target_product_month_breakdown,
        "linked_historical_product_month_breakdown": linked_historical_product_month_breakdown,
    }


def is_orderpro_catalog_product(product: Product) -> bool:
    return bool(product.source_system == "orderpro" or product.orderpro_id or product.orderpro_sku)


def _confirmed_links_by_orderpro_product(db: Session, product_ids: list[int]) -> dict[int, list[ProductHistoricalLink]]:
    if not product_ids:
        return {}
    links = (
        db.query(ProductHistoricalLink)
        .filter(
            ProductHistoricalLink.orderpro_product_id.in_(product_ids),
            ProductHistoricalLink.status.in_(["auto_confirmed", "manually_confirmed"]),
        )
        .all()
    )
    grouped: dict[int, list[ProductHistoricalLink]] = defaultdict(list)
    for link in links:
        grouped[link.orderpro_product_id].append(link)
    return grouped


def _usage_rows_by_product(db: Session, product_ids: list[int]) -> dict[int, list[UsageHistory]]:
    if not product_ids:
        return {}
    rows = db.query(UsageHistory).filter(UsageHistory.product_id.in_(product_ids)).all()
    grouped: dict[int, list[UsageHistory]] = defaultdict(list)
    for row in rows:
        grouped[row.product_id].append(row)
    return grouped


def collect_contributing_usage_rows(
    db: Session,
    product: Product,
    confirmed_links: list[ProductHistoricalLink] | None = None,
) -> tuple[list[UsageHistory], dict[str, Any]]:
    confirmed_links = confirmed_links or []
    linked_product_ids = [link.historical_product_id for link in confirmed_links]
    linked_rows_by_product = _usage_rows_by_product(db, linked_product_ids)
    direct_rows = list(product.usage_history)
    rows_by_id: dict[int, UsageHistory] = {row.id: row for row in direct_rows}
    linked_row_count = 0
    for historical_product_id in linked_product_ids:
        for row in linked_rows_by_product.get(historical_product_id, []):
            if row.id not in rows_by_id:
                linked_row_count += 1
            rows_by_id[row.id] = row

    return list(rows_by_id.values()), {
        "direct_history_row_count": len(direct_rows),
        "linked_history_row_count": linked_row_count,
        "contributing_historical_product_ids": linked_product_ids,
        "reconciliation_methods": sorted({link.match_method for link in confirmed_links}),
    }


def audit_historical_data(db: Session) -> SeasonalityAudit:
    usage_rows = db.query(UsageHistory).all()
    history_start = min((row.date for row in usage_rows), default=None)
    history_end = max((row.date for row in usage_rows), default=None)
    months = sorted({_month_key(row.date) for row in usage_rows if row.date})
    matched_product_count = len({row.product_id for row in usage_rows})
    negative_quantity_rows = sum(1 for row in usage_rows if (row.net_qty or 0) < 0 or (row.qty_returned or 0) > 0)

    unmatched_raw_rows = 0
    try:
        from app.models.sales_history_raw import SalesHistoryRaw

        unmatched_raw_rows = (
            db.query(SalesHistoryRaw)
            .filter(SalesHistoryRaw.row_type == "inventory", SalesHistoryRaw.product_id.is_(None))
            .count()
        )
    except Exception:
        unmatched_raw_rows = 0

    return SeasonalityAudit(
        source_table="usage_history",
        date_column="date",
        quantity_columns=["qty_used", "qty_returned", "net_qty"],
        product_identifier_columns=["product_id"],
        history_start=history_start,
        history_end=history_end,
        historical_rows=len(usage_rows),
        matched_rows=len([row for row in usage_rows if row.product_id is not None]),
        unmatched_raw_rows=unmatched_raw_rows,
        matched_product_count=matched_product_count,
        negative_quantity_rows=negative_quantity_rows,
        month_count=len(months),
        months_with_history=months,
    )


def build_seasonality_plan(
    db: Session,
    *,
    product_id: int | None = None,
    minimum_history_months: int = DEFAULT_MINIMUM_HISTORY_MONTHS,
    calculation_version: str = CALCULATION_VERSION,
    include_legacy_products: bool = False,
) -> SeasonalityPlan:
    query = db.query(Product).options(selectinload(Product.usage_history), selectinload(Product.seasonality_profile))
    if not include_legacy_products:
        query = query.filter(
            (Product.source_system == "orderpro")
            | (Product.orderpro_id.is_not(None))
            | (Product.orderpro_sku.is_not(None))
        )
    if product_id is not None:
        query = query.filter(Product.id == product_id)
    products = query.order_by(Product.id.asc()).all()
    product_ids = [product.id for product in products]
    links_by_product = _confirmed_links_by_orderpro_product(db, product_ids) if not include_legacy_products else {}

    profiles = []
    total_direct_rows = 0
    total_linked_rows = 0
    contributing_historical_ids: set[int] = set()
    for product in products:
        if include_legacy_products:
            usage_rows = list(product.usage_history)
            contribution = {
                "direct_history_row_count": len(usage_rows),
                "linked_history_row_count": 0,
                "contributing_historical_product_ids": [],
                "reconciliation_methods": [],
            }
        else:
            usage_rows, contribution = collect_contributing_usage_rows(
                db,
                product,
                links_by_product.get(product.id, []),
            )
        quantity_metrics = calculate_quantity_transform_metrics(
            usage_rows,
            linked_product_ids=set(contribution["contributing_historical_product_ids"]),
        )
        total_direct_rows += contribution["direct_history_row_count"]
        total_linked_rows += contribution["linked_history_row_count"]
        contributing_historical_ids.update(contribution["contributing_historical_product_ids"])
        profile = calculate_product_profile(
            product,
            usage_rows,
            minimum_history_months=minimum_history_months,
            calculation_version=calculation_version,
        )
        profile.update(
            {
                "product_name": product.name,
                "orderpro_sku": product.orderpro_sku,
                **contribution,
                **quantity_metrics,
            }
        )
        profiles.append(profile)

    existing_profile_ids = {
        product.id for product in products if product.seasonality_profile is not None
    }
    classification_counts = dict(Counter(profile["seasonality_tag"] for profile in profiles))
    confidence_counts = dict(Counter(profile["confidence_label"] for profile in profiles))
    warnings: list[str] = []
    for profile in profiles:
        for warning in profile.pop("warnings", []):
            warnings.append(f"product {profile['product_id']}: {warning}")

    needs_review_links_excluded = (
        db.query(ProductHistoricalLink)
        .filter(ProductHistoricalLink.status == "needs_review")
        .count()
        if not include_legacy_products
        else 0
    )
    ambiguous_links_excluded = needs_review_links_excluded
    rejected_links_excluded = (
        db.query(ProductHistoricalLink)
        .filter(ProductHistoricalLink.status == "rejected")
        .count()
        if not include_legacy_products
        else 0
    )
    quantity_used_for_seasonality = round(sum(profile["quantity_used_for_seasonality"] for profile in profiles), 4)
    raw_linked_net_quantity = round(sum(profile["raw_linked_net_quantity"] for profile in profiles), 4)
    positive_linked_quantity = round(sum(profile["positive_linked_quantity"] for profile in profiles), 4)
    negative_linked_quantity = round(sum(profile["negative_linked_quantity"] for profile in profiles), 4)
    negative_linked_row_count = sum(profile["negative_linked_row_count"] for profile in profiles)
    monthly_raw_net_quantity = round(sum(profile["monthly_raw_net_quantity"] for profile in profiles), 4)
    linked_product_month_clamped_quantity = round(
        sum(profile["linked_product_month_clamped_quantity"] for profile in profiles),
        4,
    )
    target_product_month_clamped_quantity = round(
        sum(profile["target_product_month_clamped_quantity"] for profile in profiles),
        4,
    )
    quantity_removed_by_target_month_clamp = round(
        sum(profile["quantity_removed_by_target_month_clamp"] for profile in profiles),
        4,
    )
    quantity_removed_by_cross_link_offset = round(
        sum(profile["quantity_removed_by_cross_link_offset"] for profile in profiles),
        4,
    )
    orderpro_products_with_direct_history = sum(1 for profile in profiles if profile["direct_history_row_count"] > 0)
    orderpro_products_with_linked_history = sum(1 for profile in profiles if profile["linked_history_row_count"] > 0)
    stale_orderpro_profiles_to_refresh = sum(
        1
        for product in products
        if (
            product.seasonality_profile is not None
            and product.seasonality_profile.seasonality_tag == "insufficient_data"
            and any(profile["product_id"] == product.id and profile["linked_history_row_count"] > 0 for profile in profiles)
        )
    )
    legacy_profiles_left_unchanged = (
        db.query(ProductSeasonalityProfile)
        .join(Product, Product.id == ProductSeasonalityProfile.product_id)
        .filter(
            Product.source_system != "orderpro",
            Product.orderpro_id.is_(None),
            Product.orderpro_sku.is_(None),
        )
        .count()
        if not include_legacy_products
        else 0
    )

    return SeasonalityPlan(
        audit=audit_historical_data(db),
        profiles=profiles,
        profiles_to_create=sum(1 for profile in profiles if profile["product_id"] not in existing_profile_ids),
        profiles_to_update=sum(1 for profile in profiles if profile["product_id"] in existing_profile_ids),
        classification_counts=classification_counts,
        confidence_counts=confidence_counts,
        insufficient_data_count=classification_counts.get("insufficient_data", 0),
        reconciliation_coverage={
            "target_orderpro_products": len(products) if not include_legacy_products else 0,
            "include_legacy_products": include_legacy_products,
            "orderpro_products_with_direct_history": orderpro_products_with_direct_history,
            "orderpro_products_with_linked_history": orderpro_products_with_linked_history,
            "orderpro_products_without_history": sum(
                1
                for profile in profiles
                if profile["direct_history_row_count"] == 0 and profile["linked_history_row_count"] == 0
            ),
            "confirmed_historical_links": sum(len(links) for links in links_by_product.values()),
            "historical_products_contributing": len(contributing_historical_ids),
            "usage_rows_contributing": total_direct_rows + total_linked_rows,
            "raw_linked_net_quantity": raw_linked_net_quantity,
            "positive_linked_quantity": positive_linked_quantity,
            "negative_linked_quantity": negative_linked_quantity,
            "negative_linked_row_count": negative_linked_row_count,
            "monthly_raw_net_quantity": monthly_raw_net_quantity,
            "linked_product_month_clamped_quantity": linked_product_month_clamped_quantity,
            "target_product_month_clamped_quantity": target_product_month_clamped_quantity,
            "quantity_used_for_seasonality": quantity_used_for_seasonality,
            "quantity_removed_by_target_month_clamp": quantity_removed_by_target_month_clamp,
            "quantity_removed_by_cross_link_offset": quantity_removed_by_cross_link_offset,
            "quantity_used_minus_raw_linked_net_quantity": round(
                quantity_used_for_seasonality - raw_linked_net_quantity,
                4,
            ),
            "quantity_used_minus_monthly_raw_net_quantity": round(
                quantity_used_for_seasonality - monthly_raw_net_quantity,
                4,
            ),
            "quantity_reconciliation_difference": round(
                quantity_used_for_seasonality - raw_linked_net_quantity,
                4,
            ),
            "net_quantity_contributing_deprecated": quantity_used_for_seasonality,
            "stale_orderpro_profiles_to_refresh": stale_orderpro_profiles_to_refresh,
            "orderpro_profiles_updated": len(existing_profile_ids),
            "legacy_profiles_left_unchanged": legacy_profiles_left_unchanged,
            "ambiguous_links_excluded": ambiguous_links_excluded,
            "needs_review_links_excluded": needs_review_links_excluded,
            "rejected_links_excluded": rejected_links_excluded,
        },
        warnings=warnings,
    )


def apply_seasonality_profiles(
    db: Session,
    *,
    product_id: int | None = None,
    minimum_history_months: int = DEFAULT_MINIMUM_HISTORY_MONTHS,
    calculation_version: str = CALCULATION_VERSION,
    include_legacy_products: bool = False,
) -> SeasonalityPlan:
    plan = build_seasonality_plan(
        db,
        product_id=product_id,
        minimum_history_months=minimum_history_months,
        calculation_version=calculation_version,
        include_legacy_products=include_legacy_products,
    )
    now = utc_now()

    products = {
        product.id: product
        for product in db.query(Product)
        .options(selectinload(Product.seasonality_profile))
        .filter(Product.id.in_([profile["product_id"] for profile in plan.profiles]))
        .all()
    }

    for profile_data in plan.profiles:
        product = products[profile_data["product_id"]]
        profile = product.seasonality_profile
        if profile is None:
            profile = ProductSeasonalityProfile(
                product_id=product.id,
                created_at=now,
            )
            db.add(profile)

        for key, value in profile_data.items():
            if key in REPORT_ONLY_PROFILE_FIELDS:
                continue
            setattr(profile, key, value)
        profile.updated_at = now
        if include_legacy_products or is_orderpro_catalog_product(product):
            product.seasonality_tag = profile_data["seasonality_tag"]

    db.commit()
    return plan


def interpret_current_seasonality(
    profile: ProductSeasonalityProfile | dict[str, Any] | None,
    *,
    month: int | None = None,
    approaching_months: int = DEFAULT_APPROACHING_MONTHS,
) -> dict[str, Any]:
    selected_month = normalize_month(month)
    if profile is None:
        return {
            "current_status": "insufficient_data",
            "selected_month": selected_month,
            "selected_month_units": None,
            "selected_month_index": None,
            "advisory_message": "No seasonality profile has been calculated for this product.",
        }

    data = profile if isinstance(profile, dict) else {
        "seasonality_tag": profile.seasonality_tag,
        "confidence_label": profile.confidence_label,
        "monthly_units": profile.monthly_units or {},
        "monthly_indices": profile.monthly_indices or {},
        "peak_months": profile.peak_months or [],
        "primary_season": profile.primary_season,
        "confidence_score": profile.confidence_score,
    }
    tag = data.get("seasonality_tag") or "insufficient_data"
    confidence_label = data.get("confidence_label") or "insufficient"
    monthly_units = data.get("monthly_units") or {}
    monthly_indices = data.get("monthly_indices") or {}
    peak_months = [int(month_value) for month_value in data.get("peak_months") or []]
    selected_month_units = monthly_units.get(str(selected_month))
    selected_month_index = monthly_indices.get(str(selected_month))

    if tag == "insufficient_data" or confidence_label == "insufficient":
        status = "insufficient_data"
    elif tag == "year_round":
        status = "year_round"
    elif selected_month in peak_months or (selected_month_index is not None and selected_month_index >= 1.2):
        status = "in_season"
    elif any(0 < _months_until(selected_month, peak_month) <= approaching_months for peak_month in peak_months):
        status = "approaching_season"
    elif selected_month_index is not None and selected_month_index <= 0.75:
        status = "off_season"
    else:
        status = "off_season"

    message = {
        "in_season": f"{MONTH_NAMES[selected_month]} is part of this product's elevated demand period.",
        "approaching_season": "A peak demand month is approaching within the configured lookahead window.",
        "off_season": f"{MONTH_NAMES[selected_month]} is not a peak month for this product.",
        "year_round": "Demand appears relatively stable throughout the year.",
        "insufficient_data": "There is not enough reliable history to classify recurring seasonality.",
    }[status]

    return {
        "current_status": status,
        "selected_month": selected_month,
        "selected_month_units": selected_month_units,
        "selected_month_index": selected_month_index,
        "advisory_message": message,
    }


def seasonality_context_for_product(
    db: Session,
    product_id: int,
    *,
    month: int | None = None,
) -> dict[str, Any] | None:
    profile = (
        db.query(ProductSeasonalityProfile)
        .filter(ProductSeasonalityProfile.product_id == product_id)
        .first()
    )
    if profile is None:
        return {
            "seasonality_tag": "insufficient_data",
            "current_status": "insufficient_data",
            "selected_month_index": None,
            "primary_season": None,
            "peak_months": [],
            "confidence_score": 0.0,
            "confidence_label": "insufficient",
            "advisory_message": (
                "No reconciled multi-year historical seasonality profile exists for this OrderPro product."
            ),
        }
    interpretation = interpret_current_seasonality(profile, month=month)
    return {
        "seasonality_tag": profile.seasonality_tag,
        "current_status": interpretation["current_status"],
        "selected_month_index": interpretation["selected_month_index"],
        "primary_season": profile.primary_season,
        "peak_months": profile.peak_months or [],
        "confidence_score": profile.confidence_score,
        "confidence_label": profile.confidence_label,
        "advisory_message": interpretation["advisory_message"],
    }
