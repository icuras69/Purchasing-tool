from app.models.inventory_position import InventoryPosition
from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse


def test_supplier_has_orderpro_identity_fields(db_session):
    supplier = Supplier(
        name="OrderPro Supplier",
        normalized_name="ORDERPRO SUPPLIER",
        orderpro_id="42",
        orderpro_code="SUP-42",
        source_system="orderpro",
        is_active=True,
    )
    db_session.add(supplier)
    db_session.commit()
    db_session.refresh(supplier)

    assert supplier.orderpro_id == "42"
    assert supplier.orderpro_code == "SUP-42"
    assert supplier.source_system == "orderpro"
    assert supplier.is_active is True
    assert supplier.last_synced_at is None


def test_product_can_reference_one_supplier_and_keep_legacy_supplier_text(db_session):
    supplier = Supplier(name="Active Supplier", normalized_name="ACTIVE SUPPLIER", orderpro_code="ACTIVE")
    product = Product(
        name="OrderPro Product",
        current_stock=5,
        orderpro_id="100",
        orderpro_sku="SKU-100",
        supplier_record=supplier,
        supplier="Legacy Supplier Text",
        supplier_sku="SUP-SKU-100",
        description="Long product description",
        brand="Brand",
        category="Category",
        uom="EACH",
        weight_kg=1.2,
        cost_price=10.0,
        sell_price=15.0,
        hs_code="HS",
        country_of_origin="IE",
        image_url="https://example.test/image.jpg",
        source_system="orderpro",
        is_active=True,
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    assert product.supplier_id == supplier.id
    assert product.supplier_record.name == "Active Supplier"
    assert product.supplier == "Legacy Supplier Text"
    assert product.orderpro_sku == "SKU-100"
    assert product.supplier_sku == "SUP-SKU-100"
    assert product.cost_price == 10.0
    assert supplier.products == [product]


def test_warehouse_model_exists_with_orderpro_identity_fields(db_session):
    warehouse = Warehouse(
        orderpro_id="7",
        name="Main Warehouse",
        code="MAIN",
        source_system="orderpro",
    )
    db_session.add(warehouse)
    db_session.commit()
    db_session.refresh(warehouse)

    assert warehouse.id is not None
    assert warehouse.orderpro_id == "7"
    assert warehouse.name == "Main Warehouse"
    assert warehouse.code == "MAIN"
    assert warehouse.is_active is True
    assert warehouse.created_at is not None
    assert warehouse.updated_at is not None


def test_inventory_position_links_product_and_warehouse_with_orderpro_stock_fields(db_session):
    product = Product(name="Stock Product", current_stock=0, orderpro_id="200", orderpro_sku="SKU-200")
    warehouse = Warehouse(orderpro_id="9", name="Remote Warehouse")
    db_session.add_all([product, warehouse])
    db_session.flush()

    position = InventoryPosition(
        product_id=product.id,
        warehouse_id=warehouse.id,
        orderpro_inventory_id="inv-1",
        orderpro_product_id="200",
        orderpro_warehouse_id="9",
        source_system="orderpro",
        location_code="legacy-location",
        location_id="loc-1",
        location_name="Aisle 1",
        lot_id="lot-1",
        lot="Batch 1",
        on_hand=12,
        allocated=2,
        incoming=3,
        available=10,
        quantity_on_hand=12,
        quantity_available=10,
        quantity_allocated=2,
        quantity_incoming=3,
    )
    db_session.add(position)
    db_session.commit()
    db_session.refresh(position)

    assert position.product == product
    assert position.warehouse == warehouse
    assert position.orderpro_inventory_id == "inv-1"
    assert position.location_id == "loc-1"
    assert position.lot_id == "lot-1"
    assert position.quantity_on_hand == 12
    assert position.quantity_available == 10
    assert warehouse.inventory_positions == [position]


def test_product_suppliers_remain_legacy_compatible(db_session):
    product = Product(name="Legacy Mapping Product", current_stock=0)
    supplier = Supplier(name="Legacy Mapping Supplier", normalized_name="LEGACY MAPPING SUPPLIER")
    db_session.add_all([product, supplier])
    db_session.flush()

    mapping = ProductSupplier(
        product_id=product.id,
        supplier_id=supplier.id,
        supplier_sku="LEGACY-SKU",
        match_status="matched",
    )
    db_session.add(mapping)
    db_session.commit()
    db_session.refresh(product)

    assert product.product_suppliers == [mapping]
    assert supplier.product_suppliers == [mapping]
