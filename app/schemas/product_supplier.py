from datetime import datetime

from pydantic import BaseModel


class ProductSupplierMappingResponse(BaseModel):
    id: int
    product_id: int
    product_name: str | None
    supplier_id: int
    supplier_name: str | None
    supplier_sku: str | None
    supplier_product_name: str | None
    purchase_price: float | None
    currency: str | None
    minimum_order_quantity: float | None
    pack_size: float | None
    lead_time_days: int | None
    is_preferred: bool
    match_status: str | None
    match_method: str | None
    match_confidence: float | None
    last_synced_at: datetime | None


class WeakMappingResponse(BaseModel):
    product_id: int
    product_name: str
    reason: str
    mapping_id: int | None = None
    supplier_id: int | None = None
    supplier_name: str | None = None
    supplier_sku: str | None = None
    supplier_product_name: str | None = None
    match_status: str | None = None
    match_method: str | None = None
    match_confidence: float | None = None
