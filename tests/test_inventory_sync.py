from datetime import date

from app.models.inventory_position import InventoryPosition
from app.models.product import Product
from app.services.inventory_provider import InventoryRecord
from app.services.inventory_sync import sync_inventory_from_provider


class StaticInventoryProvider:
    def __init__(self, records: list[InventoryRecord]):
        self.records = records

    def fetch_inventory(self) -> list[InventoryRecord]:
        return self.records


def test_inventory_sync_falls_back_to_normalized_orderpro_sku(db_session):
    product = Product(name="OrderPro Product", orderpro_id="100", orderpro_sku="SKU-100")
    db_session.add(product)
    db_session.flush()

    result = sync_inventory_from_provider(
        db_session,
        StaticInventoryProvider(
            [
                InventoryRecord(
                    sku=" sku-100 ",
                    source_system="orderpro",
                    location_code="MAIN",
                    location_name="Main",
                    on_hand=10,
                    allocated=2,
                    incoming=1,
                    available=None,
                    incoming_eta=date(2026, 7, 15),
                )
            ]
        ),
    )

    position = db_session.query(InventoryPosition).one()
    assert result["records_upserted"] == 1
    assert result["records_skipped"] == 0
    assert position.product_id == product.id
    assert position.available == 9
