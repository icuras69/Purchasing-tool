from datetime import date

from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier
from app.models.usage_history import UsageHistory


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


def seed_draft_mapping(
    db_session,
    *,
    supplier_name: str = "Draft Supplier",
    product_name: str = "Draft Product",
    product_overrides: dict | None = None,
    mapping_overrides: dict | None = None,
):
    product_defaults = {
        "name": product_name,
        "current_stock": 1,
        "safety_stock": 0,
        "min_order_qty": 1,
    }
    product_defaults.update(product_overrides or {})
    product = Product(**product_defaults)
    supplier = Supplier(name=supplier_name, normalized_name=supplier_name.upper())
    db_session.add_all([product, supplier])
    db_session.flush()

    mapping_defaults = {
        "product_id": product.id,
        "supplier_id": supplier.id,
        "supplier_sku": f"{supplier_name[:2].upper()}-DRAFT",
        "supplier_product_name": f"{supplier_name} Draft Product",
        "purchase_price": 10.0,
        "currency": "USD",
        "minimum_order_quantity": None,
        "pack_size": None,
        "lead_time_days": 4,
        "match_status": "confirmed",
        "match_method": "manual",
    }
    mapping_defaults.update(mapping_overrides or {})
    mapping = ProductSupplier(**mapping_defaults)
    db_session.add(mapping)
    db_session.commit()
    return product, supplier, mapping


def add_usage_history(db_session, product: Product, qty_used: float = 1) -> None:
    db_session.add(
        UsageHistory(
            product_id=product.id,
            date=date(2026, 1, 1),
            qty_used=qty_used,
            net_qty=qty_used,
            source_system="test",
        )
    )
    db_session.commit()


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


def submit_po(client, po_id: int) -> dict:
    response = client.post(f"/purchase-orders/{po_id}/submit-for-approval")
    assert response.status_code == 200
    return response.json()


def approve_po(client, po_id: int, approved_by: str = "manager") -> dict:
    response = client.post(
        f"/purchase-orders/{po_id}/approve",
        json={"approved_by": approved_by},
    )
    assert response.status_code == 200
    return response.json()


def issue_po(client, po_id: int) -> dict:
    response = client.post(f"/purchase-orders/{po_id}/issue")
    assert response.status_code == 200
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
    assert payload["received_at"] is None
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


def test_cannot_approve_draft_purchase_order_directly(client, db_session):
    _product, supplier, _mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)

    response = client.post(
        f"/purchase-orders/{po['id']}/approve",
        json={"approved_by": "manager"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only pending approval purchase orders can be approved."


def test_can_approve_pending_purchase_order_with_lines(client, db_session):
    _product, supplier, mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)
    add_line(client, po["id"], mapping.id)
    submit_po(client, po["id"])

    response = client.post(
        f"/purchase-orders/{po['id']}/approve",
        json={"approved_by": "manager"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approved"
    assert payload["approved_at"] is not None
    assert payload["approved_by"] == "manager"


def test_cannot_approve_purchase_order_with_zero_lines(client, db_session):
    _product, supplier, _mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)
    submit_po(client, po["id"])

    response = client.post(
        f"/purchase-orders/{po['id']}/approve",
        json={"approved_by": "manager"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot approve a purchase order with no lines."


def test_cannot_issue_purchase_order_before_approval(client, db_session):
    _product, supplier, mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)
    add_line(client, po["id"], mapping.id)
    submit_po(client, po["id"])

    response = client.post(f"/purchase-orders/{po['id']}/issue")

    assert response.status_code == 400
    assert response.json()["detail"] == "Only approved purchase orders can be issued."


def test_can_issue_approved_purchase_order(client, db_session):
    _product, supplier, mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)
    add_line(client, po["id"], mapping.id)
    submit_po(client, po["id"])
    approve_po(client, po["id"])

    response = client.post(f"/purchase-orders/{po['id']}/issue")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "issued"
    assert payload["issued_at"] is not None


def test_cannot_receive_purchase_order_before_issue(client, db_session):
    _product, supplier, mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)
    add_line(client, po["id"], mapping.id)
    submit_po(client, po["id"])
    approve_po(client, po["id"])

    response = client.post(f"/purchase-orders/{po['id']}/receive")

    assert response.status_code == 400
    assert response.json()["detail"] == "Only issued purchase orders can be received."


def test_can_receive_issued_purchase_order(client, db_session):
    _product, supplier, mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)
    add_line(client, po["id"], mapping.id)
    submit_po(client, po["id"])
    approve_po(client, po["id"])
    issue_po(client, po["id"])

    response = client.post(f"/purchase-orders/{po['id']}/receive")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "received"
    assert payload["received_at"] is not None


def test_cancel_draft_purchase_order(client, db_session):
    _product, supplier, _mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)

    response = client.post(f"/purchase-orders/{po['id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancelled_at"] is not None


def test_can_cancel_approved_purchase_order_before_issue(client, db_session):
    _product, supplier, mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)
    add_line(client, po["id"], mapping.id)
    submit_po(client, po["id"])
    approve_po(client, po["id"])

    response = client.post(f"/purchase-orders/{po['id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancelled_at"] is not None


def test_cannot_cancel_issued_or_received_purchase_order(client, db_session):
    _product, supplier, mapping = seed_product_supplier(db_session)
    po = create_po(client, supplier.id)
    add_line(client, po["id"], mapping.id)
    submit_po(client, po["id"])
    approve_po(client, po["id"])
    issue_po(client, po["id"])

    issued_cancel_response = client.post(f"/purchase-orders/{po['id']}/cancel")
    receive_response = client.post(f"/purchase-orders/{po['id']}/receive")
    received_cancel_response = client.post(f"/purchase-orders/{po['id']}/cancel")

    assert issued_cancel_response.status_code == 400
    assert issued_cancel_response.json()["detail"] == (
        "Only draft, pending approval, or approved purchase orders can be cancelled."
    )
    assert receive_response.status_code == 200
    assert receive_response.json()["status"] == "received"
    assert received_cancel_response.status_code == 400
    assert received_cancel_response.json()["detail"] == (
        "Only draft, pending approval, or approved purchase orders can be cancelled."
    )


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


def test_create_draft_po_from_one_valid_product(client, db_session):
    product, supplier, mapping = seed_draft_mapping(db_session)

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={
            "supplier_id": supplier.id,
            "product_ids": [product.id],
            "created_by": "forecast-review",
            "notes": "Draft from forecast review",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    po = payload["purchase_order"]
    assert po["status"] == "draft"
    assert po["supplier_id"] == supplier.id
    assert po["created_by"] == "forecast-review"
    assert po["notes"] == "Draft from forecast review"
    assert po["approved_at"] is None
    assert po["issued_at"] is None
    assert po["received_at"] is None
    assert payload["summary"]["created_line_count"] == 1
    assert payload["summary"]["skipped_products"] == []
    line = po["lines"][0]
    assert line["product_id"] == product.id
    assert line["product_supplier_id"] == mapping.id
    assert line["supplier_sku"] == mapping.supplier_sku
    assert line["supplier_product_name"] == mapping.supplier_product_name
    assert line["unit_cost"] == mapping.purchase_price
    assert line["currency"] == mapping.currency
    assert line["lead_time_days"] == mapping.lead_time_days


def test_create_draft_po_from_multiple_products_for_same_supplier(client, db_session):
    product_a, supplier, _mapping_a = seed_draft_mapping(db_session, supplier_name="Multi Supplier")
    product_b = Product(name="Second Draft Product", current_stock=1)
    db_session.add(product_b)
    db_session.flush()
    mapping_b = ProductSupplier(
        product_id=product_b.id,
        supplier_id=supplier.id,
        supplier_sku="MULTI-B",
        supplier_product_name="Second Supplier Product",
        purchase_price=4.0,
        currency="USD",
        match_status="matched",
        match_method="manual",
    )
    db_session.add(mapping_b)
    db_session.commit()

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={"supplier_id": supplier.id, "product_ids": [product_a.id, product_b.id]},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["purchase_order"]["status"] == "draft"
    assert payload["summary"]["created_line_count"] == 2
    assert {line["product_id"] for line in payload["purchase_order"]["lines"]} == {
        product_a.id,
        product_b.id,
    }


def test_draft_po_from_products_skips_missing_mapping_and_returns_summary(client, db_session):
    valid_product, supplier, _mapping = seed_draft_mapping(db_session, supplier_name="Skip Supplier")
    unmapped_product = Product(name="Unmapped Draft Product", current_stock=1)
    db_session.add(unmapped_product)
    db_session.commit()

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={"supplier_id": supplier.id, "product_ids": [valid_product.id, unmapped_product.id]},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["summary"]["created_line_count"] == 1
    assert payload["summary"]["skipped_products"] == [
        {
            "product_id": unmapped_product.id,
            "product_name": "Unmapped Draft Product",
            "reason": "No ProductSupplier mapping exists for this product.",
        }
    ]


def test_draft_po_from_products_rejects_when_all_products_are_skipped(client, db_session):
    supplier = Supplier(name="No Lines Supplier", normalized_name="NO LINES SUPPLIER")
    product = Product(name="No Mapping Product", current_stock=1)
    db_session.add_all([supplier, product])
    db_session.commit()

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={"supplier_id": supplier.id, "product_ids": [product.id]},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "No valid purchase order lines could be created."
    assert response.json()["detail"]["skipped_products"] == [
        {
            "product_id": product.id,
            "product_name": "No Mapping Product",
            "reason": "No ProductSupplier mapping exists for this product.",
        }
    ]


def test_draft_po_from_products_skips_mapping_for_different_supplier(client, db_session):
    product, _other_supplier, _mapping = seed_draft_mapping(db_session, supplier_name="Other Supplier")
    requested_supplier = Supplier(name="Requested Supplier", normalized_name="REQUESTED SUPPLIER")
    db_session.add(requested_supplier)
    db_session.commit()

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={"supplier_id": requested_supplier.id, "product_ids": [product.id]},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["skipped_products"][0]["reason"] == (
        "ProductSupplier mapping belongs to a different supplier."
    )


def test_draft_po_from_products_skips_rejected_mapping(client, db_session):
    product, supplier, _mapping = seed_draft_mapping(
        db_session,
        supplier_name="Rejected Draft Supplier",
        mapping_overrides={"match_status": "rejected"},
    )

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={"supplier_id": supplier.id, "product_ids": [product.id]},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["skipped_products"][0]["reason"] == (
        "ProductSupplier mapping is rejected."
    )


def test_draft_po_from_products_respects_minimum_order_quantity(client, db_session):
    product, supplier, _mapping = seed_draft_mapping(
        db_session,
        supplier_name="MOQ Draft Supplier",
        mapping_overrides={"minimum_order_quantity": 12},
    )

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={"supplier_id": supplier.id, "product_ids": [product.id]},
    )

    assert response.status_code == 201
    line = response.json()["purchase_order"]["lines"][0]
    assert line["quantity"] == 12
    assert line["minimum_order_quantity"] == 12


def test_draft_po_from_products_respects_pack_size_rounding(client, db_session):
    product, supplier, _mapping = seed_draft_mapping(
        db_session,
        supplier_name="Pack Draft Supplier",
        mapping_overrides={"minimum_order_quantity": 5, "pack_size": 4},
    )

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={"supplier_id": supplier.id, "product_ids": [product.id]},
    )

    assert response.status_code == 201
    line = response.json()["purchase_order"]["lines"][0]
    assert line["quantity"] == 8
    assert line["minimum_order_quantity"] == 5
    assert line["pack_size"] == 4


def test_draft_po_from_products_uses_forecast_recommended_quantity_when_available(client, db_session):
    product, supplier, _mapping = seed_draft_mapping(
        db_session,
        supplier_name="Forecast Draft Supplier",
        product_overrides={"current_stock": 1, "safety_stock": 10},
        mapping_overrides={
            "minimum_order_quantity": 1,
            "pack_size": 3,
            "lead_time_days": 4,
            "match_status": "matched",
        },
    )
    add_usage_history(db_session, product, qty_used=2)

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={"supplier_id": supplier.id, "product_ids": [product.id]},
    )

    assert response.status_code == 201
    line = response.json()["purchase_order"]["lines"][0]
    assert line["quantity"] == 21
    assert line["pack_size"] == 3
