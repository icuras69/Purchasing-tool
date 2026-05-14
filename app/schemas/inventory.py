from datetime import date, datetime

from pydantic import BaseModel


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