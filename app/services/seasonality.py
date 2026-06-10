from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import sqrt
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.product import Product
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
    warnings: list[str]


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
) -> SeasonalityPlan:
    query = db.query(Product).options(selectinload(Product.usage_history), selectinload(Product.seasonality_profile))
    if product_id is not None:
        query = query.filter(Product.id == product_id)
    products = query.order_by(Product.id.asc()).all()

    profiles = [
        calculate_product_profile(
            product,
            list(product.usage_history),
            minimum_history_months=minimum_history_months,
            calculation_version=calculation_version,
        )
        for product in products
    ]

    existing_profile_ids = {
        product.id for product in products if product.seasonality_profile is not None
    }
    classification_counts = dict(Counter(profile["seasonality_tag"] for profile in profiles))
    confidence_counts = dict(Counter(profile["confidence_label"] for profile in profiles))
    warnings: list[str] = []
    for profile in profiles:
        for warning in profile.pop("warnings", []):
            warnings.append(f"product {profile['product_id']}: {warning}")

    return SeasonalityPlan(
        audit=audit_historical_data(db),
        profiles=profiles,
        profiles_to_create=sum(1 for profile in profiles if profile["product_id"] not in existing_profile_ids),
        profiles_to_update=sum(1 for profile in profiles if profile["product_id"] in existing_profile_ids),
        classification_counts=classification_counts,
        confidence_counts=confidence_counts,
        insufficient_data_count=classification_counts.get("insufficient_data", 0),
        warnings=warnings,
    )


def apply_seasonality_profiles(
    db: Session,
    *,
    product_id: int | None = None,
    minimum_history_months: int = DEFAULT_MINIMUM_HISTORY_MONTHS,
    calculation_version: str = CALCULATION_VERSION,
) -> SeasonalityPlan:
    plan = build_seasonality_plan(
        db,
        product_id=product_id,
        minimum_history_months=minimum_history_months,
        calculation_version=calculation_version,
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
            if key == "product_id":
                continue
            setattr(profile, key, value)
        profile.updated_at = now
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
        return None
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
