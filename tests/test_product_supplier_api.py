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
    mapped_product, supplier, _mapping = _seed_mapping(db_session)
    mapped_product.supplier_id = supplier.id
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


def test_create_manual_product_supplier_mapping(client, db_session):
    product = Product(name="Manual Product", current_stock=0)
    supplier = Supplier(name="Manual Supplier", normalized_name="MANUAL SUPPLIER")
    db_session.add_all([product, supplier])
    db_session.commit()

    response = client.post(
        "/product-suppliers",
        json={
            "product_id": product.id,
            "supplier_id": supplier.id,
            "supplier_sku": "MANUAL-SKU",
            "supplier_product_name": "Manual Supplier Product",
            "purchase_price": 15.5,
            "currency": "USD",
            "minimum_order_quantity": 3,
            "pack_size": 2,
            "lead_time_days": 5,
            "match_status": "needs_review",
            "match_method": "manual",
            "match_confidence": 1,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["product_id"] == product.id
    assert payload["supplier_id"] == supplier.id
    assert payload["supplier_sku"] == "MANUAL-SKU"
    assert payload["supplier_product_name"] == "Manual Supplier Product"
    assert payload["purchase_price"] == 15.5
    assert payload["currency"] == "USD"
    assert payload["minimum_order_quantity"] == 3
    assert payload["pack_size"] == 2
    assert payload["lead_time_days"] == 5
    assert payload["is_preferred"] is False
    assert payload["match_status"] == "needs_review"
    assert payload["match_method"] == "manual"


def test_duplicate_product_supplier_mapping_is_rejected(client, db_session):
    product, supplier, _mapping = _seed_mapping(db_session)

    response = client.post(
        "/product-suppliers",
        json={
            "product_id": product.id,
            "supplier_id": supplier.id,
            "supplier_sku": f"SKU-{product.id}",
        },
    )

    assert response.status_code == 409


def test_update_product_supplier_safe_commercial_fields(client, db_session):
    _product, _supplier, mapping = _seed_mapping(db_session, is_preferred=True)

    response = client.patch(
        f"/product-suppliers/{mapping.id}",
        json={
            "supplier_product_name": "Updated Supplier Product",
            "purchase_price": 22.25,
            "currency": "EUR",
            "minimum_order_quantity": 7,
            "pack_size": 4,
            "lead_time_days": 9,
            "match_status": "confirmed",
            "match_method": "manual_review",
            "match_confidence": 0.99,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["supplier_product_name"] == "Updated Supplier Product"
    assert payload["purchase_price"] == 22.25
    assert payload["currency"] == "EUR"
    assert payload["minimum_order_quantity"] == 7
    assert payload["pack_size"] == 4
    assert payload["lead_time_days"] == 9
    assert payload["match_status"] == "confirmed"
    assert payload["match_method"] == "manual_review"
    assert payload["match_confidence"] == 0.99
    assert payload["is_preferred"] is True


def test_set_preferred_unsets_other_product_mappings(client, db_session):
    product = Product(name="Preferred Product", current_stock=0)
    supplier_a = Supplier(name="Supplier A Preferred", normalized_name="SUPPLIER A PREFERRED")
    supplier_b = Supplier(name="Supplier B Preferred", normalized_name="SUPPLIER B PREFERRED")
    db_session.add_all([product, supplier_a, supplier_b])
    db_session.flush()
    mapping_a = ProductSupplier(
        product_id=product.id,
        supplier_id=supplier_a.id,
        supplier_sku="PREF-A",
        is_preferred=True,
        match_status="matched",
    )
    mapping_b = ProductSupplier(
        product_id=product.id,
        supplier_id=supplier_b.id,
        supplier_sku="PREF-B",
        is_preferred=False,
        match_status="matched",
    )
    db_session.add_all([mapping_a, mapping_b])
    db_session.commit()

    response = client.post(f"/product-suppliers/{mapping_b.id}/set-preferred")

    assert response.status_code == 200
    assert response.json()["is_preferred"] is True
    db_session.refresh(mapping_a)
    db_session.refresh(mapping_b)
    assert mapping_a.is_preferred is False
    assert mapping_b.is_preferred is True


def test_cannot_set_rejected_mapping_as_preferred(client, db_session):
    _product, _supplier, mapping = _seed_mapping(db_session, match_status="rejected")

    response = client.post(f"/product-suppliers/{mapping.id}/set-preferred")

    assert response.status_code == 400


def test_confirm_mapping_sets_status_confirmed(client, db_session):
    _product, _supplier, mapping = _seed_mapping(db_session, match_status="needs_review")

    response = client.post(f"/product-suppliers/{mapping.id}/confirm")

    assert response.status_code == 200
    assert response.json()["match_status"] == "confirmed"


def test_reject_mapping_sets_status_rejected_and_unsets_preferred(client, db_session):
    _product, _supplier, mapping = _seed_mapping(
        db_session,
        match_status="matched",
        is_preferred=True,
    )

    response = client.post(f"/product-suppliers/{mapping.id}/reject")

    assert response.status_code == 200
    payload = response.json()
    assert payload["match_status"] == "rejected"
    assert payload["is_preferred"] is False


def test_forecast_uses_orderpro_product_supplier_after_preference_change(client, db_session):
    supplier_a = Supplier(
        name="Forecast Supplier A",
        normalized_name="FORECAST SUPPLIER A",
        orderpro_code="FSA",
    )
    supplier_b = Supplier(name="Forecast Supplier B", normalized_name="FORECAST SUPPLIER B")
    product = Product(
        name="Forecast Preference Product",
        current_stock=10,
        supplier_record=supplier_a,
        supplier_sku="ORDERPRO-A",
    )
    db_session.add_all([product, supplier_a, supplier_b])
    db_session.flush()
    mapping_a = ProductSupplier(
        product_id=product.id,
        supplier_id=supplier_a.id,
        supplier_sku="FORECAST-A",
        is_preferred=True,
        match_status="matched",
        lead_time_days=3,
    )
    mapping_b = ProductSupplier(
        product_id=product.id,
        supplier_id=supplier_b.id,
        supplier_sku="FORECAST-B",
        is_preferred=False,
        match_status="matched",
        lead_time_days=4,
    )
    db_session.add_all([mapping_a, mapping_b])
    db_session.commit()

    set_response = client.post(f"/product-suppliers/{mapping_b.id}/set-preferred")
    forecast_response = client.get(f"/products/{product.id}/forecast")

    assert set_response.status_code == 200
    assert forecast_response.status_code == 200
    context = forecast_response.json()["supplier_context"]
    assert context["supplier_id"] == supplier_a.id
    assert context["supplier_name"] == "Forecast Supplier A"
    assert context["supplier_code"] == "FSA"
    assert context["supplier_sku"] == "ORDERPRO-A"
    assert context["mapping_source"] == "orderpro_product_supplier"
