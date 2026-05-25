import sys

from app.models.product import Product
from app.models.product_master_item import ProductMasterItem
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier
from scripts import backfill_product_suppliers


def _run_backfill(monkeypatch, session_factory, *args):
    monkeypatch.setattr(backfill_product_suppliers, "SessionLocal", session_factory)
    monkeypatch.setattr(sys, "argv", ["backfill_product_suppliers.py", *args])
    backfill_product_suppliers.main()


def _seed_product_and_supplier(db_session):
    product = Product(name="Widget", current_stock=5)
    supplier = Supplier(name="Supplier A", normalized_name="SUPPLIER A")
    db_session.add_all([product, supplier])
    db_session.flush()
    return product, supplier


def test_backfill_dry_run_inserts_nothing(monkeypatch, session_factory, db_session):
    product, supplier = _seed_product_and_supplier(db_session)
    db_session.add(
        ProductMasterItem(
            sku="SKU-1",
            name="Widget Supplier Name",
            product_id=product.id,
            supplier_id=supplier.id,
            cost_price=4.25,
            match_status="matched",
            match_method="exact_sku",
        )
    )
    db_session.commit()

    _run_backfill(monkeypatch, session_factory, "--dry-run")

    assert db_session.query(ProductSupplier).count() == 0


def test_backfill_apply_inserts_only_eligible_matched_rows(monkeypatch, session_factory, db_session):
    product, supplier = _seed_product_and_supplier(db_session)
    other_supplier = Supplier(name="Supplier B", normalized_name="SUPPLIER B")
    db_session.add(other_supplier)
    db_session.flush()

    db_session.add_all(
        [
            ProductMasterItem(
                sku="ELIGIBLE",
                name="Eligible Name",
                product_id=product.id,
                supplier_id=supplier.id,
                cost_price=7.5,
                match_status="matched",
                match_method="exact_sku",
            ),
            ProductMasterItem(
                sku="MISSING-PRODUCT",
                name="Missing Product",
                product_id=None,
                supplier_id=supplier.id,
                match_status="matched",
            ),
            ProductMasterItem(
                sku="MISSING-SUPPLIER",
                name="Missing Supplier",
                product_id=product.id,
                supplier_id=None,
                match_status="matched",
            ),
            ProductMasterItem(
                sku="UNMATCHED",
                name="Unmatched",
                product_id=product.id,
                supplier_id=other_supplier.id,
                match_status="unmatched",
            ),
        ]
    )
    db_session.commit()

    _run_backfill(monkeypatch, session_factory, "--apply")

    mappings = db_session.query(ProductSupplier).all()
    assert len(mappings) == 1
    mapping = mappings[0]
    assert mapping.product_id == product.id
    assert mapping.supplier_id == supplier.id
    assert mapping.supplier_sku == "ELIGIBLE"
    assert mapping.supplier_product_name == "Eligible Name"
    assert mapping.purchase_price == 7.5
    assert mapping.is_preferred is False
    assert mapping.match_status == "matched"
    assert mapping.match_method == "exact_sku"
    assert mapping.currency is None
    assert mapping.minimum_order_quantity is None
    assert mapping.pack_size is None
    assert mapping.lead_time_days is None
    assert mapping.match_confidence is None
    assert mapping.last_synced_at is not None
    assert mapping.created_at == mapping.updated_at


def test_backfill_apply_does_not_duplicate_existing_rows(monkeypatch, session_factory, db_session):
    product, supplier = _seed_product_and_supplier(db_session)
    db_session.add_all(
        [
            ProductMasterItem(
                sku="SKU-1",
                name="Widget Supplier Name",
                product_id=product.id,
                supplier_id=supplier.id,
                match_status="matched",
            ),
            ProductSupplier(
                product_id=product.id,
                supplier_id=supplier.id,
                supplier_sku="SKU-1",
                supplier_product_name="Already Exists",
            ),
        ]
    )
    db_session.commit()

    _run_backfill(monkeypatch, session_factory, "--apply")

    mappings = db_session.query(ProductSupplier).all()
    assert len(mappings) == 1
    assert mappings[0].supplier_product_name == "Already Exists"
