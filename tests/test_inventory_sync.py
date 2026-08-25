from datetime import date, datetime, timezone

from app.models.inventory_position import InventoryPosition
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.services.inventory_provider import InventoryRecord
from app.services.inventory_sync import sync_inventory_from_provider
from app.services.orderpro_sync_planner import apply_inventory_sync


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


def test_complete_orderpro_snapshot_zeroes_absent_stock_and_stale_positions(db_session):
    warehouse = Warehouse(orderpro_id="1", name="Main", source_system="orderpro")
    present = Product(
        name="Present Product",
        orderpro_id="100",
        orderpro_sku="PRESENT-100",
        source_system="orderpro",
        current_stock=99,
    )
    absent = Product(
        name="Absent Product",
        orderpro_id="200",
        orderpro_sku="ABSENT-200",
        source_system="orderpro",
        current_stock=7,
    )
    db_session.add_all([warehouse, present, absent])
    db_session.flush()
    stale_position = InventoryPosition(
        product_id=absent.id,
        warehouse_id=warehouse.id,
        orderpro_inventory_id="stale-position",
        source_system="orderpro",
        location_id="MAIN",
        on_hand=7,
        available=7,
        quantity_on_hand=7,
        quantity_available=7,
    )
    db_session.add(stale_position)
    db_session.flush()

    result = apply_inventory_sync(
        db_session,
        [
            {
                "id": "current-position",
                "product_id": "100",
                "warehouse_id": "1",
                "location_id": "MAIN",
                "qty": 4,
                "product": {"sku": "PRESENT-100"},
                "warehouse": {"name": "Main"},
            }
        ],
        synced_at=datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc),
        complete_snapshot=True,
    )
    db_session.flush()

    assert present.current_stock == 4
    assert absent.current_stock == 0
    assert stale_position.quantity_on_hand == 0
    assert stale_position.available == 0
    assert result["summary"]["inventory_positions_zeroed"] == 1
    assert result["summary"]["products_current_stock_zeroed"] == 1


def test_orderpro_inventory_refresh_uses_canonical_client_and_updates_local_cache(
    client,
    db_session,
    monkeypatch,
):
    product = Product(
        name="OrderPro Product",
        orderpro_id="100",
        orderpro_sku="SKU-100",
        source_system="orderpro",
        current_stock=0,
    )
    db_session.add(product)
    db_session.commit()

    class FakeOrderProClient:
        def get_inventory(self):
            return [
                {
                    "id": "position-100",
                    "product_id": "100",
                    "warehouse_id": "1",
                    "location_id": "MAIN",
                    "qty": 12,
                    "product": {"sku": "SKU-100"},
                    "warehouse": {"name": "Main"},
                }
            ]

    monkeypatch.setattr("app.routes.inventory.settings.orderpro_sync_enabled", True)
    monkeypatch.setattr("app.routes.inventory.OrderProClient", FakeOrderProClient)

    response = client.post("/inventory/sync/orderpro")

    assert response.status_code == 200
    body = response.json()
    assert body["complete_snapshot"] is True
    assert body["records_received"] == 1
    assert body["inventory_positions_created"] == 1
    assert body["products_current_stock_updated"] == 1
    assert "OrderPro was not modified" in body["message"]
    db_session.expire_all()
    assert db_session.get(Product, product.id).current_stock == 12


def test_orderpro_inventory_refresh_is_blocked_when_sync_is_disabled(client, monkeypatch):
    monkeypatch.setattr("app.routes.inventory.settings.orderpro_sync_enabled", False)

    response = client.post("/inventory/sync/orderpro")

    assert response.status_code == 409
    assert "ORDERPRO_SYNC_ENABLED=true" in response.json()["detail"]
