from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

import httpx

from app.core.config import settings
from app.services.inventory_provider import InventoryProvider, InventoryRecord


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return float(value)
    except Exception:
        return 0.0


def _to_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


class OrderProProvider(InventoryProvider):
    def __init__(self) -> None:
        self.base_url = settings.orderpro_base_url.rstrip("/")
        self.api_key = settings.orderpro_api_key
        self.endpoint = settings.orderpro_inventory_endpoint.strip()
        self.timeout = settings.orderpro_timeout_seconds

    def fetch_inventory(self) -> list[InventoryRecord]:
        if not self.base_url or not self.endpoint:
            raise ValueError(
                "OrderPro settings are missing. Set ORDERPRO_BASE_URL and ORDERPRO_INVENTORY_ENDPOINT in .env."
            )

        if not self.api_key:
            raise ValueError("ORDERPRO_API_KEY is missing.")

        headers = self._build_headers()

        page = 1
        all_rows: list[dict[str, Any]] = []

        with httpx.Client(timeout=self.timeout) as client:
            while True:
                payload = self._fetch_page(client, headers, page)
                rows = self._extract_rows(payload)
                all_rows.extend(rows)

                meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
                last_page = meta.get("last_page", page)

                if page >= last_page:
                    break

                page += 1

        mapped_records = []
        for row in all_rows:
            record = self._map_row(row)
            if record is not None:
                mapped_records.append(record)

        return self._aggregate_records(mapped_records)

    def _fetch_page(self, client: httpx.Client, headers: dict[str, str], page: int) -> dict[str, Any]:
        url = f"{self.base_url}/{self.endpoint.lstrip('/')}"
        response = client.get(url, headers=headers, params={"page": page})
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("Unexpected OrderPro response format: expected JSON object.")

        return payload

    def _build_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _extract_rows(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            return payload["data"]

        raise ValueError("Could not find inventory rows in OrderPro response.")

    def _map_row(self, row: dict[str, Any]) -> InventoryRecord | None:
        product = row.get("product") or {}
        warehouse = row.get("warehouse") or {}
        location = row.get("location") or {}

        sku = product.get("sku")
        if not sku:
            return None

        qty = _to_float(row.get("qty"))

        warehouse_id = row.get("warehouse_id")
        location_id = row.get("location_id")

        location_code = None
        if location_id is not None:
            location_code = str(location_id)
        elif warehouse_id is not None:
            location_code = f"warehouse-{warehouse_id}"

        location_name = location.get("name") or warehouse.get("name")

        return InventoryRecord(
            sku=str(sku).strip(),
            source_system="orderpro",
            location_code=location_code,
            location_name=location_name,
            on_hand=qty,
            allocated=0.0,
            incoming=0.0,
            available=qty,
            incoming_eta=None,
        )

    def _aggregate_records(self, records: list[InventoryRecord]) -> list[InventoryRecord]:
        grouped: dict[tuple[str, str | None, str | None], InventoryRecord] = {}

        for record in records:
            key = (record.sku.strip().upper(), record.location_code, record.location_name)

            if key not in grouped:
                grouped[key] = InventoryRecord(
                    sku=record.sku,
                    source_system=record.source_system,
                    location_code=record.location_code,
                    location_name=record.location_name,
                    on_hand=record.on_hand,
                    allocated=record.allocated,
                    incoming=record.incoming,
                    available=record.available,
                    incoming_eta=record.incoming_eta,
                )
            else:
                grouped[key].on_hand += record.on_hand
                grouped[key].allocated += record.allocated
                grouped[key].incoming += record.incoming
                grouped[key].available = (grouped[key].available or 0.0) + (record.available or 0.0)

        return list(grouped.values())