from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier


def seed_product_supplier(
    db_session,
    *,
    supplier_name: str = "PO Supplier",
    product_name: str = "PO Product",
    match_status: str = "confirmed",
):
    product = Product(name=product_name, current_stock=0)
    supplier = Supplier(name=supplier_name, normalized_name=supplier_name.upper())
    db_session.add_all([product, supplier])
    db_session.flush()
    mapping = ProductSupplier(
        product_id=product.id,
        supplier_id=supplier.id,
        supplier_sku=f"{supplier_name[:2].upper()}-SKU",
        supplier_product_name=f"{supplier_name} Product",
        purchase_price=12.5,
        currency="USD",
        minimum_order_quantity=5,
        pack_size=2,
        lead_time_days=7,
        match_status=match_status,
        match_method="manual",
    )
    db_session.add(mapping)
    db_session.commit()
    return product, supplier, mapping


def create_po(client, supplier_id: int) -> dict:
    response = client.post(
        "/purchase-orders",
        json={"supplier_id": supplier_id, "notes": "Draft notes", "created_by": "tester"},
    )
    assert response.status_code == 201
    return response.json()


def add_line(client, po_id: int, product_supplier_id: int, quantity: float = 6) -> dict:
    response = client.post(
        f"/purchase-orders/{po_id}/lines",
        json={
            "product_supplier_id": product_supplier_id,
            "quantity": quantity,
            "notes": "Line notes",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_draft_purchase_order(client, db_session):
    _product, supplier, _mapping = seed_product_supplier(db_session)

    payload = create_po(client, supplier.id)

    assert payload["supplier_id"] == supplier.id
    assert payload["supplier_name"] == supplier.name
    assert payload["status"] == "draft"
    assert payload["notes"] == "Draft notes"
    assert payload["created_by"] == "tester"
    assert payload["approved_at"] is None
    assert payload["issued_at"] is None
    assert payload["cancelled_at"] is None
    assert payload["lines"] == []


def test_add_purchase_order_line_snapshots_product_supplier_data(client, db_session):
    product, supplier, mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)

    payload = add_line(client, po["id"], mapping.id, quantity=6)

    line = payload["lines"][0]
    assert line["product_id"] == product.id
    assert line["product_supplier_id"] == mapping.id
    assert line["supplier_sku"] == mapping.supplier_sku
    assert line["supplier_product_name"] == mapping.supplier_product_name
    assert line["quantity"] == 6
    assert line["unit_cost"] == 12.5
    assert line["currency"] == "USD"
    assert line["line_total"] == 75.0
    assert line["minimum_order_quantity"] == 5
    assert line["pack_size"] == 2
    assert line["lead_time_days"] == 7
    assert payload["total_amount"] == 75.0
    assert payload["currency"] == "USD"

    mapping.supplier_sku = "CHANGED-SKU"
    mapping.purchase_price = 99
    db_session.commit()

    refreshed = client.get(f"/purchase-orders/{po['id']}").json()
    refreshed_line = refreshed["lines"][0]
    assert refreshed_line["supplier_sku"] != "CHANGED-SKU"
    assert refreshed_line["unit_cost"] == 12.5


def test_reject_line_when_product_supplier_belongs_to_different_supplier(client, db_session):
    _product_a, supplier_a, _mapping_a = seed_product_supplier(db_session, supplier_name="Supplier A")
    _product_b, _supplier_b, mapping_b = seed_product_supplier(db_session, supplier_name="Supplier B")
    po = create_po(client, supplier_a.id)

    response = client.post(
        f"/purchase-orders/{po['id']}/lines",
        json={"product_supplier_id": mapping_b.id, "quantity": 1},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "ProductSupplier belongs to a different supplier."


def test_reject_line_when_product_supplier_is_rejected(client, db_session):
    _product, supplier, mapping = seed_product_supplier(db_session, match_status="rejected")
    po = create_po(client, supplier.id)

    response = client.post(
        f"/purchase-orders/{po['id']}/lines",
        json={"product_supplier_id": mapping.id, "quantity": 1},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Rejected ProductSupplier mappings cannot be used."


def test_update_draft_purchase_order_line_quantity(client, db_session):
    _product, supplier, mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)
    po_with_line = add_line(client, po["id"], mapping.id, quantity=2)
    line_id = po_with_line["lines"][0]["id"]

    response = client.patch(
        f"/purchase-orders/{po['id']}/lines/{line_id}",
        json={"quantity": 4, "notes": "Updated notes"},
    )

    assert response.status_code == 200
    line = response.json()["lines"][0]
    assert line["quantity"] == 4
    assert line["line_total"] == 50.0
    assert line["notes"] == "Updated notes"
    assert response.json()["total_amount"] == 50.0


def test_submit_draft_purchase_order_for_approval(client, db_session):
    _product, supplier, _mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)

    response = client.post(f"/purchase-orders/{po['id']}/submit-for-approval")

    assert response.status_code == 200
    assert response.json()["status"] == "pending_approval"


def test_cancel_draft_purchase_order(client, db_session):
    _product, supplier, _mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)

    response = client.post(f"/purchase-orders/{po['id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancelled_at"] is not None


def test_cannot_edit_lines_after_purchase_order_is_not_draft(client, db_session):
    _product, supplier, mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)
    po_with_line = add_line(client, po["id"], mapping.id, quantity=2)
    line_id = po_with_line["lines"][0]["id"]
    client.post(f"/purchase-orders/{po['id']}/submit-for-approval")

    add_response = client.post(
        f"/purchase-orders/{po['id']}/lines",
        json={"product_supplier_id": mapping.id, "quantity": 1},
    )
    update_response = client.patch(
        f"/purchase-orders/{po['id']}/lines/{line_id}",
        json={"quantity": 5},
    )

    assert add_response.status_code == 400
    assert update_response.status_code == 400
    assert add_response.json()["detail"] == "Only draft purchase orders can be edited."
    assert update_response.json()["detail"] == "Only draft purchase orders can be edited."


def test_list_purchase_orders(client, db_session):
    _product, supplier, _mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)

    response = client.get("/purchase-orders")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [po["id"]]
