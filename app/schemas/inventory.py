from datetime import date, datetime

from pydantic import BaseModel, Field


class InventoryPositionResponse(BaseModel):
    product_id: int
    source_system: str
    location_code: str | None
    location_name: str | None
    on_hand: float
    allocated: float
    incoming: float
    available: float
    incoming_eta: date | None
    last_synced_at: datetime


class InventorySyncResult(BaseModel):
    source_system: str
    records_received: int
    records_upserted: int
    records_skipped: int
    message: str
    sync_completed_at: datetime | None = None
    complete_snapshot: bool = False
    warehouses_created: int = 0
    warehouses_updated: int = 0
    inventory_positions_created: int = 0
    inventory_positions_updated: int = 0
    inventory_positions_zeroed: int = 0
    products_current_stock_updated: int = 0
    products_current_stock_zeroed: int = 0
    rows_missing_product_match: int = 0
    rows_missing_warehouse_id: int = 0
    unmatched_rows_sample: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
