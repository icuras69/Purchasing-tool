from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier


def _seed_mapping(db_session, *, match_status="matched", match_confidence=None, is_preferred=False):
    suffix = f"{match_status or 'none'}-{match_confidence}-{is_preferred}"
    product = Product(name=f"Product {suffix}", current_stock=0)
    supplier = Supplier(name=f"Supplier {suffix}", normalized_name=f"SUPPLIER {suffix}".upper())
    db_session.add_all([product, supplier])
    db_session.flush()
    mapping = ProductSupplier(
        product_id=product.id,
        supplier_id=supplier.id,
        supplier_sku=f"SKU-{product.id}",
        supplier_product_name="Supplier Product",
        purchase_price=9.99,
        is_preferred=is_preferred,
        match_status=match_status,
        match_method="test_method",
        match_confidence=match_confidence,
    )
    db_session.add(mapping)
    db_session.commit()
    return product, supplier, mapping


def test_list_product_suppliers_endpoint(client, db_session):
    _product, supplier, mapping = _seed_mapping(db_session)

    response = client.get("/product-suppliers")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == mapping.id
    assert payload[0]["supplier_id"] == supplier.id
    assert payload[0]["supplier_name"] == supplier.name
    assert payload[0]["supplier_sku"] == mapping.supplier_sku
    assert payload[0]["supplier_product_name"] == "Supplier Product"
    assert payload[0]["purchase_price"] == 9.99
    assert payload[0]["is_preferred"] is False
    assert payload[0]["match_status"] == "matched"
    assert payload[0]["match_method"] == "test_method"


def test_product_supplier_mappings_endpoint(client, db_session):
    product, _supplier, mapping = _seed_mapping(db_session, is_preferred=True)

    response = client.get(f"/products/{product.id}/supplier-mappings")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == mapping.id
    assert payload[0]["product_id"] == product.id
    assert payload[0]["is_preferred"] is True


def test_supplier_products_endpoint(client, db_session):
    product, supplier, mapping = _seed_mapping(db_session)

    response = client.get(f"/suppliers/{supplier.id}/products")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == mapping.id
    assert payload[0]["product_id"] == product.id
    assert payload[0]["supplier_id"] == supplier.id


def test_unmapped_products_endpoint(client, db_session):
    mapped_product, _supplier, _mapping = _seed_mapping(db_session)
    unmapped_product = Product(name="No Mapping", current_stock=0)
    db_session.add(unmapped_product)
    db_session.commit()

    response = client.get("/products/unmapped")

    assert response.status_code == 200
    payload = response.json()
    returned_ids = {item["id"] for item in payload}
    assert unmapped_product.id in returned_ids
    assert mapped_product.id not in returned_ids
    assert payload[0]["mapping_status"] == "unmapped"


def test_weak_mappings_endpoint(client, db_session):
    unmapped_product = Product(name="Unmapped", current_stock=0)
    db_session.add(unmapped_product)
    _seed_mapping(db_session, match_status="matched", match_confidence=0.95)
    weak_product, _supplier, weak_mapping = _seed_mapping(
        db_session,
        match_status="suggested",
        match_confidence=0.5,
    )
    low_conf_product, _low_supplier, low_conf_mapping = _seed_mapping(
        db_session,
        match_status="matched",
        match_confidence=0.2,
    )
    db_session.commit()

    response = client.get("/products/weak-mappings?confidence_threshold=0.8")

    assert response.status_code == 200
    payload = response.json()
    reasons_by_product = {item["product_id"]: item["reason"] for item in payload}
    assert reasons_by_product[unmapped_product.id] == "no_supplier_mappings"
    assert reasons_by_product[weak_product.id] == "match_status_not_matched"
    assert reasons_by_product[low_conf_product.id] == "match_confidence_below_threshold"
    assert any(item["mapping_id"] == weak_mapping.id for item in payload)
    assert any(item["mapping_id"] == low_conf_mapping.id for item in payload)
