from datetime import datetime

from app.models.product import Product
from app.models.product_master_item import ProductMasterItem
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier
from app.services.product_supplier_sync import sync_product_suppliers_from_master_items


def seed_product_and_supplier(db_session, product_name="Widget", supplier_name="Supplier A"):
    product = Product(name=product_name, current_stock=5)
    supplier = Supplier(name=supplier_name, normalized_name=supplier_name.upper())
    db_session.add_all([product, supplier])
    db_session.flush()
    return product, supplier


def master_item(product, supplier, **overrides):
    defaults = {
        "sku": "SKU-1",
        "name": "Widget Supplier Name",
        "product_id": product.id if product else None,
        "supplier_id": supplier.id if supplier else None,
        "cost_price": 4.25,
        "match_status": "matched",
        "match_method": "exact_sku",
    }
    defaults.update(overrides)
    return ProductMasterItem(**defaults)


def test_eligible_matched_product_master_item_creates_product_supplier(db_session):
    product, supplier = seed_product_and_supplier(db_session)
    db_session.add(master_item(product, supplier))
    db_session.commit()

    summary = sync_product_suppliers_from_master_items(
        db_session,
        dry_run=False,
        now=datetime(2026, 1, 1, 12, 0, 0),
    )
    db_session.commit()

    mapping = db_session.query(ProductSupplier).one()
    assert summary.created_count == 1
    assert summary.updated_count == 0
    assert summary.skipped_count == 0
    assert summary.conflict_count == 0
    assert mapping.product_id == product.id
    assert mapping.supplier_id == supplier.id
    assert mapping.supplier_sku == "SKU-1"
    assert mapping.supplier_product_name == "Widget Supplier Name"
    assert mapping.purchase_price == 4.25
    assert mapping.is_preferred is False
    assert mapping.match_status == "matched"
    assert mapping.match_method == "exact_sku"
    assert mapping.minimum_order_quantity is None
    assert mapping.pack_size is None
    assert mapping.lead_time_days is None
    assert mapping.last_synced_at == datetime(2026, 1, 1, 12, 0, 0)


def test_existing_product_supplier_is_updated_safely_not_duplicated(db_session):
    product, supplier = seed_product_and_supplier(db_session)
    db_session.add_all(
        [
            master_item(
                product,
                supplier,
                name="Updated Supplier Name",
                cost_price=8.5,
                match_method="exact_name",
            ),
            ProductSupplier(
                product_id=product.id,
                supplier_id=supplier.id,
                supplier_sku="SKU-1",
                supplier_product_name="Old Supplier Name",
                purchase_price=2.0,
                is_preferred=True,
                minimum_order_quantity=12,
                pack_size=6,
                lead_time_days=9,
                match_status="old",
                match_method="old_method",
            ),
        ]
    )
    db_session.commit()

    summary = sync_product_suppliers_from_master_items(
        db_session,
        dry_run=False,
        now=datetime(2026, 1, 2, 9, 30, 0),
    )
    db_session.commit()

    mappings = db_session.query(ProductSupplier).all()
    assert len(mappings) == 1
    mapping = mappings[0]
    assert summary.created_count == 0
    assert summary.updated_count == 1
    assert mapping.supplier_product_name == "Updated Supplier Name"
    assert mapping.purchase_price == 8.5
    assert mapping.match_status == "matched"
    assert mapping.match_method == "exact_name"
    assert mapping.last_synced_at == datetime(2026, 1, 2, 9, 30, 0)
    assert mapping.is_preferred is True
    assert mapping.minimum_order_quantity == 12
    assert mapping.pack_size == 6
    assert mapping.lead_time_days == 9


def test_unmatched_and_missing_fk_product_master_items_are_skipped(db_session):
    product, supplier = seed_product_and_supplier(db_session)
    db_session.add_all(
        [
            master_item(product, supplier, sku="UNMATCHED", match_status="unmatched"),
            master_item(None, supplier, sku="MISSING-PRODUCT"),
            master_item(product, None, sku="MISSING-SUPPLIER"),
        ]
    )
    db_session.commit()

    summary = sync_product_suppliers_from_master_items(db_session, dry_run=False)
    db_session.commit()

    assert db_session.query(ProductSupplier).count() == 0
    assert summary.created_count == 0
    assert summary.updated_count == 0
    assert summary.skipped_count == 3
    assert summary.conflict_count == 0


def test_existing_supplier_sku_for_different_product_is_conflict(db_session):
    product, supplier = seed_product_and_supplier(db_session)
    other_product = Product(name="Other Widget", current_stock=2)
    db_session.add(other_product)
    db_session.flush()
    db_session.add_all(
        [
            master_item(product, supplier),
            ProductSupplier(
                product_id=other_product.id,
                supplier_id=supplier.id,
                supplier_sku="SKU-1",
                supplier_product_name="Other Product",
            ),
        ]
    )
    db_session.commit()

    summary = sync_product_suppliers_from_master_items(db_session, dry_run=False)
    db_session.commit()

    assert db_session.query(ProductSupplier).count() == 1
    assert summary.created_count == 0
    assert summary.updated_count == 0
    assert summary.skipped_count == 0
    assert summary.conflict_count == 1


def test_dry_run_does_not_insert_or_update_product_suppliers(db_session):
    product, supplier = seed_product_and_supplier(db_session)
    db_session.add(master_item(product, supplier))
    db_session.commit()

    summary = sync_product_suppliers_from_master_items(db_session, dry_run=True)

    assert summary.created_count == 1
    assert db_session.query(ProductSupplier).count() == 0
