from datetime import datetime

from pydantic import BaseModel


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    notes: str | None = None
    currency: str | None = None
    created_by: str | None = None


class PurchaseOrderLineCreate(BaseModel):
    product_supplier_id: int
    quantity: float
    notes: str | None = None


class PurchaseOrderLineUpdate(BaseModel):
    quantity: float | None = None
    notes: str | None = None


class PurchaseOrderApprove(BaseModel):
    approved_by: str | None = None


class PurchaseOrderLineResponse(BaseModel):
    id: int
    purchase_order_id: int
    product_id: int
    product_supplier_id: int
    supplier_sku: str | None
    supplier_product_name: str | None
    quantity: float
    unit_cost: float | None
    currency: str | None
    line_total: float | None
    minimum_order_quantity: float | None
    pack_size: float | None
    lead_time_days: int | None
    notes: str | None


class PurchaseOrderResponse(BaseModel):
    id: int
    supplier_id: int | None
    supplier_name: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    issued_at: datetime | None
    received_at: datetime | None
    cancelled_at: datetime | None
    notes: str | None
    total_amount: float | None
    currency: str | None
    created_by: str | None
    approved_by: str | None
    lines: list[PurchaseOrderLineResponse] = []
