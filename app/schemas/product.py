from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    supplier: str | None = None
    current_stock: float = Field(ge=0)
    safety_stock: float = Field(ge=0, default=0)
    lead_time_days: int = Field(ge=0, default=0)
    min_order_qty: float = Field(ge=0, default=0)


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    supplier: str | None
    description: str | None = None
    barcode: str | None = None
    orderpro_sku: str | None = None
    supplier_id: int | None = None
    supplier_name: str | None = None
    supplier_code: str | None = None
    supplier_sku: str | None = None
    current_stock: float
    safety_stock: float
    lead_time_days: int
    min_order_qty: float
    supplier_count: int = 0
    preferred_supplier: str | None = None
    preferred_supplier_id: int | None = None
    preferred_supplier_sku: str | None = None
    supplier_mappings: list["ProductSupplierResponse"] = Field(default_factory=list)
    mapping_status: str = "unmapped"


class ProductSupplierResponse(BaseModel):
    id: int
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
