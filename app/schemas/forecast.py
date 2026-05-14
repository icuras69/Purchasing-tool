from pydantic import BaseModel


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

    reorder_point: float
    recommended_action: str
    recommended_qty: float
    risk_level: str
    explanation: str