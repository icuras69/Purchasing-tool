from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app.services.inventory_provider import InventoryProvider, InventoryRecord


def _clean_text(value):
    if value is None:
        return None
    if pd.isna(value):
        return None
    value = str(value).strip()
    return value or None


def _to_float(value) -> float:
    if value is None or pd.isna(value):
        return 0.0
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    try:
        return float(value)
    except Exception:
        return 0.0


def _to_date(value) -> date | None:
    if value is None or pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return None
    return parsed.date()


class OrderProCsvProvider(InventoryProvider):
    def __init__(self, csv_path: str) -> None:
        self.csv_path = Path(csv_path)

    def fetch_inventory(self) -> list[InventoryRecord]:
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")

        df = pd.read_csv(self.csv_path, dtype=object)
        df.columns = [str(c).strip() for c in df.columns]

        required = {"SKU", "Product", "Warehouse", "Qty"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"CSV is missing required columns: {sorted(missing)}")

        records = []

        for _, row in df.iterrows():
            sku = _clean_text(row.get("SKU"))
            if not sku:
                continue

            on_hand = _to_float(row.get("Qty"))

            records.append(
                InventoryRecord(
                    sku=sku,
                    source_system="orderpro",
                    location_code=_clean_text(row.get("Location")),
                    location_name=_clean_text(row.get("Warehouse")),
                    on_hand=on_hand,
                    allocated=0.0,
                    incoming=0.0,
                    available=on_hand,
                    incoming_eta=None,
                )
            )

        return records