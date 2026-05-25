from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier


def test_product_response_reports_unmapped_product(client, db_session):
    product = Product(name="Unmapped Product", supplier="Legacy Supplier", current_stock=0)
    db_session.add(product)
    db_session.commit()

    response = client.get(f"/products/{product.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["supplier"] == "Legacy Supplier"
    assert payload["supplier_count"] == 0
    assert payload["preferred_supplier"] == "Legacy Supplier"
    assert payload["preferred_supplier_id"] is None
    assert payload["preferred_supplier_sku"] is None
    assert payload["supplier_mappings"] == []
    assert payload["mapping_status"] == "unmapped"


def test_product_response_reports_single_mapping(client, db_session):
    product = Product(name="Mapped Product", current_stock=0)
    supplier = Supplier(name="Supplier A", normalized_name="SUPPLIER A")
    db_session.add_all([product, supplier])
    db_session.flush()
    db_session.add(
        ProductSupplier(
            product_id=product.id,
            supplier_id=supplier.id,
            supplier_sku="SKU-A",
            supplier_product_name="Supplier Product A",
            purchase_price=3.75,
            match_status="matched",
            match_method="exact_sku",
        )
    )
    db_session.commit()

    response = client.get(f"/products/{product.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["supplier_count"] == 1
    assert payload["preferred_supplier"] == "Supplier A"
    assert payload["preferred_supplier_id"] == supplier.id
    assert payload["preferred_supplier_sku"] == "SKU-A"
    assert payload["mapping_status"] == "mapped"
    assert payload["supplier_mappings"][0]["supplier_name"] == "Supplier A"
    assert payload["supplier_mappings"][0]["purchase_price"] == 3.75


def test_product_response_prefers_mapping_marked_preferred(client, db_session):
    product = Product(name="Multi Mapping Product", current_stock=0)
    supplier_a = Supplier(name="Supplier A", normalized_name="SUPPLIER A")
    supplier_b = Supplier(name="Supplier B", normalized_name="SUPPLIER B")
    db_session.add_all([product, supplier_a, supplier_b])
    db_session.flush()
    db_session.add_all(
        [
            ProductSupplier(
                product_id=product.id,
                supplier_id=supplier_a.id,
                supplier_sku="SKU-A",
                is_preferred=False,
                match_status="matched",
            ),
            ProductSupplier(
                product_id=product.id,
                supplier_id=supplier_b.id,
                supplier_sku="SKU-B",
                is_preferred=True,
                match_status="matched",
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/products/{product.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["supplier_count"] == 2
    assert payload["preferred_supplier"] == "Supplier B"
    assert payload["preferred_supplier_id"] == supplier_b.id
    assert payload["preferred_supplier_sku"] == "SKU-B"
