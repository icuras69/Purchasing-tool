from datetime import date

from pydantic import BaseModel


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


class ForecastResponse(BaseModel):
    product_id: int
    product_name: str
    orderpro_sku: str | None = None

    current_stock: float
    inventory_source: str

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
    units_sold_in_window: float | None = None
    eligible_order_count: int | None = None
    excluded_order_count: int | None = None
    days_until_stockout: float | None

    supplier_name: str | None
    matched_sku: str | None
    lead_time_days_used: int
    lead_time_source: str
    supplier_context: ForecastSupplierContext | None = None

    reorder_point: float
    recommended_action: str
    recommended_qty: float
    risk_level: str
    explanation: str
