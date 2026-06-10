from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class SeasonalityInterpretation(BaseModel):
    current_status: str
    selected_month: int
    selected_month_units: float | None
    selected_month_index: float | None
    advisory_message: str


class SeasonalitySummaryResponse(BaseModel):
    classification_counts: dict[str, int]
    confidence_counts: dict[str, int]
    current_season_counts: dict[str, int]
    profile_count: int
    product_count: int
    missing_profile_count: int
    selected_month: int
    include_legacy: bool = False


class SeasonalProductResponse(BaseModel):
    product_id: int
    orderpro_sku: str | None
    name: str
    supplier_id: int | None
    supplier_name: str | None
    current_stock: float
    seasonality_tag: str | None
    current_seasonality_status: str
    selected_month: int
    selected_month_units: float | None
    selected_month_index: float | None
    peak_months: list[int]
    primary_season: str | None
    seasonality_strength: float | None
    confidence_score: float | None
    confidence_label: str | None
    history_start: date | None
    history_end: date | None
    years_covered: int | None


class ProductSeasonalityProfileResponse(BaseModel):
    product_id: int
    orderpro_sku: str | None
    name: str
    history_start: date | None
    history_end: date | None
    history_months: int
    active_months: int
    years_covered: int
    total_units: float
    average_monthly_units: float
    monthly_units: dict[str, Any] | None
    monthly_indices: dict[str, Any] | None
    peak_months: list[int]
    low_months: list[int]
    primary_season: str | None
    seasonality_tag: str
    seasonality_strength: float
    confidence_score: float
    confidence_label: str
    coefficient_of_variation: float | None
    calculation_version: str
    calculated_at: datetime
    current_interpretation: SeasonalityInterpretation
    direct_history_row_count: int = 0
    linked_history_row_count: int = 0
    contributing_historical_product_ids: list[int] = []
    reconciliation_methods: list[str] = []


class ForecastSeasonalityContext(BaseModel):
    seasonality_tag: str | None
    current_status: str
    selected_month_index: float | None
    primary_season: str | None
    peak_months: list[int]
    confidence_score: float | None
    confidence_label: str | None
    advisory_message: str
