from datetime import date, datetime, timezone

from app.models.inventory_position import InventoryPosition
from app.models.orderpro_order import OrderProOrder, OrderProOrderItem
from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier
from app.models.usage_history import UsageHistory
from app.models.warehouse import Warehouse
from app.services.forecasting import build_forecast, resolve_supplier_context


def supplier(name: str, lead_time_days: int | None = None, **overrides) -> Supplier:
    defaults = {
        "name": name,
        "normalized_name": name.lower().replace(" ", "_"),
        "lead_time_days": lead_time_days,
    }
    defaults.update(overrides)
    return Supplier(**defaults)


def product(name: str = "Test Product", **overrides) -> Product:
    defaults = {
        "name": name,
        "current_stock": 10,
        "safety_stock": 0,
        "lead_time_days": 0,
        "min_order_qty": 1,
    }
    defaults.update(overrides)
    return Product(**defaults)


def add_usage(db_session, product_obj: Product, quantity: float = 1) -> None:
    db_session.add(
        UsageHistory(
            product=product_obj,
            date=date(2026, 1, 1),
            qty_used=quantity,
            net_qty=quantity,
            source_system="test",
        )
    )


def add_orderpro_order_item(
    db_session,
    product_obj: Product,
    *,
    orderpro_order_id: str,
    quantity: float,
    quantity_ordered: float | None = None,
    quantity_shipped: float | None = None,
    quantity_picked: float | None = None,
    status: str = "shipped",
    order_date: datetime = datetime(2026, 6, 1, tzinfo=timezone.utc),
) -> None:
    order = OrderProOrder(
        orderpro_id=orderpro_order_id,
        order_number=f"SO-{orderpro_order_id}",
        status=status,
        order_date=order_date,
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderProOrderItem(
            order=order,
            product=product_obj,
            orderpro_line_key=f"{orderpro_order_id}:1",
            orderpro_product_id=product_obj.orderpro_id,
            sku=product_obj.orderpro_sku,
            quantity=quantity,
            quantity_ordered=quantity_ordered,
            quantity_picked=quantity_picked,
            quantity_shipped=quantity_shipped,
        )
    )


def test_orderpro_product_supplier_is_used(db_session):
    supplier_obj = supplier("OrderPro Supplier", lead_time_days=6, orderpro_code="OP-SUP")
    item = product(supplier_record=supplier_obj, supplier_sku="OP-SKU", cost_price=12.5)
    db_session.add(item)
    db_session.commit()

    context = resolve_supplier_context(item)

    assert context["mapping_source"] == "orderpro_product_supplier"
    assert context["supplier_id"] == supplier_obj.id
    assert context["supplier_name"] == "OrderPro Supplier"
    assert context["supplier_code"] == "OP-SUP"
    assert context["matched_sku"] == "OP-SKU"
    assert context["supplier_sku"] == "OP-SKU"
    assert context["purchase_price"] == 12.5
    assert context["lead_time_days_used"] == 6
    assert context["lead_time_source"] == "supplier_record"


def test_product_supplier_is_not_selected_over_product_supplier_id(db_session):
    orderpro_supplier = supplier("OrderPro Supplier", lead_time_days=6, orderpro_code="OP")
    legacy_mapping_supplier = supplier("Legacy Mapping Supplier", lead_time_days=1)
    item = product(supplier_record=orderpro_supplier, supplier_sku="ORDERPRO-SKU")
    db_session.add_all(
        [
            item,
            ProductSupplier(
                product=item,
                supplier=legacy_mapping_supplier,
                supplier_sku="LEGACY-MAPPING-SKU",
                is_preferred=True,
                match_status="matched",
            ),
        ]
    )
    db_session.commit()

    context = resolve_supplier_context(item)

    assert context["mapping_source"] == "orderpro_product_supplier"
    assert context["supplier_name"] == "OrderPro Supplier"
    assert context["supplier_sku"] == "ORDERPRO-SKU"
    assert context["lead_time_days_used"] == 6


def test_product_supplier_id_uses_product_lead_time_when_supplier_lead_time_missing(db_session):
    supplier_obj = supplier("No Lead Supplier", lead_time_days=None)
    item = product(supplier_record=supplier_obj, supplier_sku="OP-SKU", lead_time_days=4)
    db_session.add(item)
    db_session.commit()

    context = resolve_supplier_context(item)

    assert context["lead_time_days_used"] == 4
    assert context["lead_time_source"] == "product_record"


def test_minimum_order_quantity_uses_product_min_order_qty(db_session):
    supplier_obj = supplier("MOQ Supplier", lead_time_days=1)
    item = product(current_stock=0, min_order_qty=25, supplier_record=supplier_obj)
    db_session.add(item)
    add_usage(db_session, item, quantity=1)
    db_session.flush()

    forecast = build_forecast(db_session, item)

    assert forecast["recommended_action"] == "reorder"
    assert forecast["recommended_qty"] == 25.0


def test_orderpro_order_items_drive_average_daily_usage(db_session):
    supplier_obj = supplier("Demand Supplier", lead_time_days=3)
    item = product(
        current_stock=20,
        orderpro_id="100",
        orderpro_sku="SKU-100",
        source_system="orderpro",
        supplier_record=supplier_obj,
    )
    db_session.add(item)
    db_session.flush()
    add_orderpro_order_item(
        db_session,
        item,
        orderpro_order_id="500",
        quantity=10,
        order_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    add_orderpro_order_item(
        db_session,
        item,
        orderpro_order_id="501",
        quantity=5,
        order_date=datetime(2026, 6, 5, tzinfo=timezone.utc),
    )
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["demand_source"] == "orderpro_orders"
    assert forecast["avg_daily_usage"] == 3.0
    assert forecast["units_sold_in_window"] == 15
    assert forecast["eligible_order_count"] == 2
    assert forecast["shipped_units_in_window"] == 15
    assert forecast["shipped_order_count"] == 2
    assert forecast["observation_days"] == 5
    assert forecast["demand_history_start"] == date(2026, 6, 1)
    assert forecast["demand_history_end"] == date(2026, 6, 5)


def test_cancelled_orderpro_orders_are_excluded_from_demand(db_session):
    supplier_obj = supplier("Cancelled Demand Supplier", lead_time_days=3)
    item = product(
        current_stock=20,
        orderpro_id="101",
        orderpro_sku="SKU-101",
        source_system="orderpro",
        supplier_record=supplier_obj,
    )
    db_session.add(item)
    db_session.flush()
    add_orderpro_order_item(db_session, item, orderpro_order_id="502", quantity=99, status="cancelled")
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["demand_source"] == "orderpro_orders"
    assert forecast["orderpro_sku"] == "SKU-101"
    assert forecast["avg_daily_usage"] == 0.0
    assert forecast["eligible_order_count"] == 0
    assert forecast["excluded_order_count"] == 1
    assert forecast["recommended_action"] == "monitor"


def test_open_orderpro_demand_is_separate_from_average_daily_usage(db_session):
    supplier_obj = supplier("Open Demand Supplier", lead_time_days=3)
    item = product(
        current_stock=20,
        orderpro_id="106",
        orderpro_sku="SKU-106",
        source_system="orderpro",
        supplier_record=supplier_obj,
    )
    db_session.add(item)
    db_session.flush()
    add_orderpro_order_item(db_session, item, orderpro_order_id="506", quantity=10, quantity_shipped=10, status="shipped")
    add_orderpro_order_item(db_session, item, orderpro_order_id="507", quantity=0, quantity_ordered=3, quantity_shipped=0, status="confirmed")
    add_orderpro_order_item(db_session, item, orderpro_order_id="508", quantity=0, quantity_ordered=4, quantity_shipped=0, status="packed")
    add_orderpro_order_item(db_session, item, orderpro_order_id="509", quantity=0, quantity_ordered=5, quantity_shipped=0, status="backorder")
    add_orderpro_order_item(db_session, item, orderpro_order_id="510", quantity=99, status="cancelled")
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["avg_daily_usage"] == 10.0
    assert forecast["shipped_units_in_window"] == 10
    assert forecast["shipped_order_count"] == 1
    assert forecast["open_confirmed_units"] == 3
    assert forecast["open_packed_units"] == 4
    assert forecast["open_backorder_units"] == 5
    assert forecast["total_open_demand"] == 12
    assert forecast["effective_available_stock"] == 8
    assert forecast["excluded_order_count"] == 1


def test_partially_shipped_open_order_counts_only_remaining_open_demand(db_session):
    supplier_obj = supplier("Partial Open Demand Supplier", lead_time_days=3)
    item = product(
        current_stock=20,
        orderpro_id="108",
        orderpro_sku="SKU-108",
        source_system="orderpro",
        supplier_record=supplier_obj,
    )
    db_session.add(item)
    db_session.flush()
    add_orderpro_order_item(db_session, item, orderpro_order_id="513", quantity=4, quantity_shipped=4, status="shipped")
    add_orderpro_order_item(
        db_session,
        item,
        orderpro_order_id="514",
        quantity=4,
        quantity_ordered=10,
        quantity_shipped=4,
        status="confirmed",
    )
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["shipped_units_in_window"] == 4
    assert forecast["open_confirmed_units"] == 6
    assert forecast["total_open_demand"] == 6
    assert forecast["effective_available_stock"] == 14


def test_zero_stock_open_demand_shortage_recommends_open_quantity(db_session):
    supplier_obj = supplier("Confirmed Demand Supplier", lead_time_days=3)
    item = product(
        current_stock=0,
        safety_stock=0,
        min_order_qty=1,
        orderpro_id="6775",
        orderpro_sku="SKU-6775",
        source_system="orderpro",
        supplier_record=supplier_obj,
    )
    db_session.add(item)
    db_session.flush()
    add_orderpro_order_item(
        db_session,
        item,
        orderpro_order_id="515",
        quantity=0,
        quantity_ordered=64,
        quantity_shipped=0,
        status="confirmed",
    )
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["demand_source"] == "orderpro_orders"
    assert forecast["orderpro_sku"] == "SKU-6775"
    assert forecast["avg_daily_usage"] == 0.0
    assert forecast["open_confirmed_units"] == 64
    assert forecast["total_open_demand"] == 64
    assert forecast["effective_available_stock"] == 0
    assert forecast["net_available_stock"] == -64
    assert forecast["projected_lead_time_demand"] == 0
    assert forecast["total_required_stock"] == 64
    assert forecast["recommended_qty"] == 64.0
    assert forecast["recommended_action"] == "reorder"
    assert forecast["risk_level"] == "high"
    assert "Open committed demand" in forecast["explanation"]
    assert "exceeds current stock" in forecast["explanation"]


def test_open_demand_equal_to_stock_does_not_create_artificial_shortage(db_session):
    supplier_obj = supplier("Covered Demand Supplier", lead_time_days=3)
    item = product(
        current_stock=64,
        safety_stock=0,
        min_order_qty=1,
        orderpro_id="109",
        orderpro_sku="SKU-109",
        source_system="orderpro",
        supplier_record=supplier_obj,
    )
    db_session.add(item)
    db_session.flush()
    add_orderpro_order_item(
        db_session,
        item,
        orderpro_order_id="516",
        quantity=0,
        quantity_ordered=64,
        quantity_shipped=0,
        status="confirmed",
    )
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["total_open_demand"] == 64
    assert forecast["effective_available_stock"] == 0
    assert forecast["net_available_stock"] == 0
    assert forecast["recommended_qty"] == 0.0
    assert forecast["recommended_action"] == "monitor"


def test_partially_covered_open_demand_recommends_remaining_shortage(db_session):
    supplier_obj = supplier("Partly Covered Supplier", lead_time_days=3)
    item = product(
        current_stock=20,
        safety_stock=0,
        min_order_qty=1,
        orderpro_id="110",
        orderpro_sku="SKU-110",
        source_system="orderpro",
        supplier_record=supplier_obj,
    )
    db_session.add(item)
    db_session.flush()
    add_orderpro_order_item(
        db_session,
        item,
        orderpro_order_id="517",
        quantity=0,
        quantity_ordered=64,
        quantity_shipped=0,
        status="confirmed",
    )
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["total_open_demand"] == 64
    assert forecast["net_available_stock"] == -44
    assert forecast["recommended_qty"] == 44.0
    assert forecast["recommended_action"] == "reorder"
    assert forecast["risk_level"] == "high"


def test_shipped_historical_and_open_demand_combine_for_reorder_quantity(db_session):
    supplier_obj = supplier("Combined Demand Supplier", lead_time_days=2)
    item = product(
        current_stock=10,
        safety_stock=1,
        min_order_qty=1,
        orderpro_id="111",
        orderpro_sku="SKU-111",
        source_system="orderpro",
        supplier_record=supplier_obj,
    )
    db_session.add(item)
    db_session.flush()
    add_orderpro_order_item(
        db_session,
        item,
        orderpro_order_id="518",
        quantity=5,
        quantity_shipped=5,
        status="shipped",
        order_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    add_orderpro_order_item(
        db_session,
        item,
        orderpro_order_id="519",
        quantity=5,
        quantity_shipped=5,
        status="shipped",
        order_date=datetime(2026, 6, 5, tzinfo=timezone.utc),
    )
    add_orderpro_order_item(
        db_session,
        item,
        orderpro_order_id="520",
        quantity=0,
        quantity_ordered=12,
        quantity_shipped=0,
        status="confirmed",
    )
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["avg_daily_usage"] == 2.0
    assert forecast["projected_lead_time_demand"] == 4.0
    assert forecast["total_open_demand"] == 12
    assert forecast["total_required_stock"] == 17
    assert forecast["recommended_qty"] == 7.0
    assert forecast["recommended_action"] == "reorder"


def test_open_demand_shortage_applies_moq_after_shortage_calculation(db_session):
    supplier_obj = supplier("Open MOQ Supplier", lead_time_days=3)
    item = product(
        current_stock=60,
        safety_stock=0,
        min_order_qty=10,
        orderpro_id="112",
        orderpro_sku="SKU-112",
        source_system="orderpro",
        supplier_record=supplier_obj,
    )
    db_session.add(item)
    db_session.flush()
    add_orderpro_order_item(db_session, item, orderpro_order_id="521", quantity=0, quantity_ordered=64, quantity_shipped=0, status="confirmed")
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["net_available_stock"] == -4
    assert forecast["recommended_qty"] == 10.0


def test_open_demand_shortage_applies_pack_size_after_shortage_calculation(db_session):
    supplier_obj = supplier("Open Pack Supplier", lead_time_days=3)
    item = product(
        current_stock=0,
        safety_stock=0,
        min_order_qty=1,
        orderpro_id="113",
        orderpro_sku="SKU-113",
        source_system="orderpro",
        supplier_record=supplier_obj,
    )
    item.pack_size = 10
    db_session.add(item)
    db_session.flush()
    add_orderpro_order_item(db_session, item, orderpro_order_id="522", quantity=0, quantity_ordered=64, quantity_shipped=0, status="confirmed")
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["recommended_qty"] == 70.0


def test_product_with_no_orderpro_usable_history_falls_back_to_legacy_usage(db_session):
    supplier_obj = supplier("Fallback Supplier", lead_time_days=3)
    item = product(
        current_stock=2,
        orderpro_id="102",
        orderpro_sku="SKU-102",
        source_system="orderpro",
        supplier_record=supplier_obj,
    )
    db_session.add(item)
    add_usage(db_session, item, quantity=4)
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["demand_source"] == "usage_history"
    assert forecast["avg_daily_usage"] == 4.0
    assert forecast["units_sold_in_window"] == 4


def test_product_with_no_history_anywhere_remains_monitor(db_session):
    supplier_obj = supplier("No History Supplier", lead_time_days=3)
    item = product(
        current_stock=20,
        orderpro_id="103",
        orderpro_sku="SKU-103",
        source_system="orderpro",
        supplier_record=supplier_obj,
    )
    db_session.add(item)
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["demand_source"] == "none"
    assert forecast["avg_daily_usage"] == 0.0
    assert forecast["days_until_stockout"] is None
    assert forecast["recommended_action"] == "monitor"


def test_orderpro_demand_calculates_stockout_reorder_point_and_moq(db_session):
    supplier_obj = supplier("Reorder Supplier", lead_time_days=4)
    item = product(
        current_stock=2,
        safety_stock=2,
        min_order_qty=20,
        orderpro_id="104",
        orderpro_sku="SKU-104",
        source_system="orderpro",
        supplier_record=supplier_obj,
    )
    db_session.add(item)
    db_session.flush()
    add_orderpro_order_item(
        db_session,
        item,
        orderpro_order_id="503",
        quantity=10,
        order_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    add_orderpro_order_item(
        db_session,
        item,
        orderpro_order_id="504",
        quantity=10,
        order_date=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["avg_daily_usage"] == 10.0
    assert forecast["effective_available_stock"] == 2
    assert forecast["days_until_stockout"] == 0.2
    assert forecast["reorder_point"] == 42.0
    assert forecast["recommended_action"] == "reorder"
    assert forecast["recommended_qty"] == 40.0


def test_recommended_quantity_uses_effective_stock_and_pack_rounding(db_session):
    supplier_obj = supplier("Pack Supplier", lead_time_days=2)
    item = product(
        current_stock=12,
        safety_stock=0,
        min_order_qty=1,
        orderpro_id="107",
        orderpro_sku="SKU-107",
        source_system="orderpro",
        supplier_record=supplier_obj,
    )
    item.pack_size = 5
    db_session.add(item)
    db_session.flush()
    add_orderpro_order_item(db_session, item, orderpro_order_id="511", quantity=6, quantity_shipped=6, status="shipped")
    add_orderpro_order_item(db_session, item, orderpro_order_id="512", quantity=0, quantity_ordered=8, quantity_shipped=0, status="confirmed")
    db_session.flush()

    forecast = build_forecast(db_session, item)

    assert forecast["effective_available_stock"] == 4
    assert forecast["reorder_point"] == 12
    assert forecast["recommended_qty"] == 10.0


def test_forecasting_does_not_call_orderpro_api(monkeypatch, db_session):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Forecasting must use synced local OrderPro data, not live API calls.")

    monkeypatch.setattr("app.services.orderpro_client.OrderProClient.generic_get", fail_if_called)
    supplier_obj = supplier("Local Demand Supplier", lead_time_days=3)
    item = product(
        current_stock=5,
        orderpro_id="105",
        orderpro_sku="SKU-105",
        source_system="orderpro",
        supplier_record=supplier_obj,
    )
    db_session.add(item)
    db_session.flush()
    add_orderpro_order_item(db_session, item, orderpro_order_id="505", quantity=4)
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["demand_source"] == "orderpro_orders"


def test_product_without_supplier_id_falls_back_to_legacy_supplier_text(db_session):
    item = product(supplier="Legacy Supplier", lead_time_days=3, min_order_qty=6)
    db_session.add(item)
    db_session.commit()

    context = resolve_supplier_context(item)

    assert context["mapping_source"] == "legacy_product"
    assert context["supplier_name"] == "Legacy Supplier"
    assert context["lead_time_days_used"] == 3
    assert context["minimum_order_quantity_used"] == 6


def test_product_without_supplier_info_returns_missing_state(db_session):
    item = product()
    db_session.add(item)
    db_session.commit()

    context = resolve_supplier_context(item)

    assert context["mapping_source"] == "missing"
    assert context["supplier_name"] is None
    assert context["matched_sku"] is None
    assert context["lead_time_days_used"] == 0
    assert context["lead_time_source"] == "missing"


def test_product_current_stock_cache_is_used_even_when_inventory_positions_exist(db_session):
    supplier_obj = supplier("Stock Supplier", lead_time_days=2)
    item = product(current_stock=13, supplier_record=supplier_obj)
    warehouse = Warehouse(orderpro_id="W1", name="Main")
    db_session.add_all([item, warehouse])
    db_session.flush()
    db_session.add(
        InventoryPosition(
            product_id=item.id,
            warehouse_id=warehouse.id,
            source_system="orderpro",
            location_id="L1",
            quantity_on_hand=99,
            on_hand=99,
            available=99,
        )
    )
    add_usage(db_session, item, quantity=1)
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["current_stock"] == 13
    assert forecast["inventory_source"] == "orderpro_current_stock_cache"
