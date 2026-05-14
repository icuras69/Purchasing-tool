from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.inventory_position import InventoryPosition
from app.models.product_master_item import ProductMasterItem
from app.services.inventory_provider import InventoryProvider


def sync_inventory_from_provider(db: Session, provider: InventoryProvider) -> dict:
    records = provider.fetch_inventory()

    master_items = {
        item.sku.strip().upper(): item
        for item in db.query(ProductMasterItem).all()
    }

    upserted = 0
    skipped = 0

    for record in records:
        sku_key = record.sku.strip().upper()
        master_item = master_items.get(sku_key)

        if not master_item or not master_item.product_id:
            skipped += 1
            continue

        existing = (
            db.query(InventoryPosition)
            .filter(
                InventoryPosition.product_id == master_item.product_id,
                InventoryPosition.source_system == record.source_system,
                InventoryPosition.location_code == record.location_code,
            )
            .first()
        )

        if existing is None:
            existing = InventoryPosition(
                product_id=master_item.product_id,
                source_system=record.source_system,
                location_code=record.location_code,
                location_name=record.location_name,
                on_hand=record.on_hand,
                allocated=record.allocated,
                incoming=record.incoming,
                available=record.available if record.available is not None else (record.on_hand - record.allocated + record.incoming),
                incoming_eta=record.incoming_eta,
            )
            db.add(existing)
        else:
            existing.location_name = record.location_name
            existing.on_hand = record.on_hand
            existing.allocated = record.allocated
            existing.incoming = record.incoming
            existing.available = record.available if record.available is not None else (record.on_hand - record.allocated + record.incoming)
            existing.incoming_eta = record.incoming_eta

        upserted += 1

    db.commit()

    return {
        "source_system": "orderpro",
        "records_received": len(records),
        "records_upserted": upserted,
        "records_skipped": skipped,
        "message": "Inventory sync completed.",
    }