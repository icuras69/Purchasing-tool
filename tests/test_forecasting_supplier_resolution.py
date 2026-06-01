from datetime import date

from app.models.inventory_position import InventoryPosition
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
    item = product(current_stock=1, min_order_qty=25, supplier_record=supplier_obj)
    db_session.add(item)
    add_usage(db_session, item, quantity=1)
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["recommended_action"] == "order_now"
    assert forecast["recommended_qty"] == 25.0


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
