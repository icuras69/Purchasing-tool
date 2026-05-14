from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass
class InventoryRecord:
    sku: str
    source_system: str
    location_code: str | None
    location_name: str | None
    on_hand: float
    allocated: float
    incoming: float
    available: float | None
    incoming_eta: date | None


class InventoryProvider(Protocol):
    def fetch_inventory(self) -> list[InventoryRecord]:
        ...