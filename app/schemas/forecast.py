from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.seasonality import ForecastSeasonalityContext


class ForecastSupplierContext(BaseModel):
    supplier_id: int | None
    supplier_name: str | None
    supplier_code: str | None = None
    supplier_sku: str | None
    supplier_product_name: str | None
    purchase_price: float | None
    currency: str | None
    lead_time_days: int
    lead_time_source: str
    minimum_order_quantity: float
    moq_source: str
    match_status: str | None
    match_method: str | None
    mapping_source: str
    has_supplier_mapping: bool
    needs_supplier_mapping: bool


class IncomingStockContext(BaseModel):
    product_id: int
    incoming_qty: float
    incoming_qty_local: float = 0.0
    incoming_qty_orderpro: float = 0.0
    incoming_qty_total: float = 0.0
    incoming_qty_by_source: dict[str, float]
    source_breakdown: dict
    open_po_count: int
    open_po_line_count: int
    earliest_expected_date: date | None
    latest_expected_date: date | None
    supplier_ids: list[int]
    warnings: list[str]


class ForecastInputContext(BaseModel):
    product_id: int
    cost_price: float | None = None
    cost_source: str
    cost_confidence: str
    cost_updated_at: datetime | None = None
    lead_time_days: int | None = None
    lead_time_source: str
    lead_time_confidence: str
    min_order_qty: float | None = None
    moq_source: str
    pack_size: float | None = None
    pack_size_source: str
    safety_stock: float | None = None
    safety_stock_source: str
    blocking_issues: list[str]
    warning_issues: list[str]
    readiness_score: float


class ForecastResponse(BaseModel):
    product_id: int
    product_name: str
    orderpro_sku: str | None = None

    current_stock: float
    inventory_source: str
    inventory_last_synced_at: datetime | None = None

    avg_daily_usage: float
    demand_source: str | None = None
    demand_lookback_days: int | None = None
    demand_history_start: date | None = None
    demand_history_end: date | None = None
    observation_days: int | None = None
    shipped_units_in_window: float | None = None
    shipped_order_count: int | None = None
    open_confirmed_units: float | None = None
    open_packed_units: float | None = None
    open_backorder_units: float | None = None
    total_open_demand: float | None = None
    effective_available_stock: float | None = None
    net_available_stock: float | None = None
    projected_lead_time_demand: float | None = None
    total_required_stock: float | None = None
    incoming_qty: float | None = None
    effective_available_stock_for_reorder: float | None = None
    recommended_qty_before_inbound: float | None = None
    recommended_qty_after_inbound: float | None = None
    inbound_adjustment_qty: float | None = None
    units_sold_in_window: float | None = None
    eligible_order_count: int | None = None
    excluded_order_count: int | None = None
    days_until_stockout: float | None

    supplier_name: str | None
    matched_sku: str | None
    lead_time_days_used: int
    lead_time_source: str
    supplier_context: ForecastSupplierContext | None = None
    seasonality_context: ForecastSeasonalityContext | None = None
    incoming_stock_context: IncomingStockContext | None = None
    forecast_input_context: ForecastInputContext | None = None

    cost_price: float | None = None
    cost_source: str | None = None
    cost_confidence: str | None = None
    estimated_unit_cost: float | None = None
    estimated_cost_source: str | None = None
    estimated_purchase_value: float | None = None
    moq_source: str | None = None
    pack_size: float | None = None
    pack_size_source: str | None = None
    safety_stock_used: float | None = None
    safety_stock_source: str | None = None
    input_blocking_issues: list[str] = []
    input_warning_issues: list[str] = []
    forecast_readiness_score: float | None = None

    reorder_point: float
    recommended_action: str
    recommended_qty: float
    risk_level: str
    explanation: str
