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

    current_stock: float
    inventory_source: str

    avg_daily_usage: float
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
