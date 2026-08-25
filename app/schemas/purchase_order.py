from datetime import datetime

from pydantic import BaseModel, Field


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    notes: str | None = None
    currency: str | None = None
    created_by: str | None = None


class DraftPurchaseOrderFromProductsCreate(BaseModel):
    supplier_id: int | None = None
    product_ids: list[int]
    notes: str | None = None
    created_by: str | None = None
    only_reorder_needed: bool = False


class PurchaseOrderLineCreate(BaseModel):
    product_supplier_id: int | None = None
    product_id: int | None = None
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
    product_supplier_id: int | None
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


class DraftPurchaseOrderSkippedProductResponse(BaseModel):
    product_id: int
    product_name: str | None
    reason: str


class DraftPurchaseOrderSummaryResponse(BaseModel):
    created_po_count: int | None = None
    created_line_count: int
    skipped_products: list[DraftPurchaseOrderSkippedProductResponse]
    grouped_by_supplier: dict[str, int] | None = None


class DraftPurchaseOrderFromProductsResponse(BaseModel):
    purchase_order: PurchaseOrderResponse | None = None
    created_purchase_orders: list[PurchaseOrderResponse] = []
    summary: DraftPurchaseOrderSummaryResponse


class SupplierForecastResponse(BaseModel):
    supplier_id: int
    supplier_name: str | None
    supplier_code: str | None = None
    product_count: int
    forecasts: list[dict]
    products_needing_reorder: list[int]
    products_missing_data: list[int]
    low_stock_products: list[int] = Field(default_factory=list)
    out_of_stock_products: list[int] = Field(default_factory=list)
    incoming_covered_products: list[int] = Field(default_factory=list)
    high_risk_products: list[int] = Field(default_factory=list)
    stock_status: str = "healthy"
    inventory_last_synced_at: datetime | None = None
    total_current_stock: float = 0
    total_incoming_quantity: float = 0
    total_recommended_quantity: float
    total_estimated_cost: float | None


class SupplierDraftPurchaseOrderFromForecastCreate(BaseModel):
    notes: str | None = None
    created_by: str | None = None
    only_reorder_needed: bool = True
