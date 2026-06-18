import csv
import io
from datetime import date, datetime, timezone

from app.models.orderpro_order import OrderProOrder, OrderProOrderItem
from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.purchase_order import PurchaseOrder
from app.models.supplier import Supplier
from app.models.usage_history import UsageHistory
from app.core.security import settings


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
        "cost_price": 10.0,
        "lead_time_days": 4,
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
    product.supplier_id = supplier.id
    product.supplier_sku = mapping_defaults["supplier_sku"]
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


def add_orderpro_demand_history(db_session, product: Product, qty_used: float = 1) -> None:
    order = OrderProOrder(
        orderpro_id=f"order-{product.id}",
        order_number=f"SO-{product.id}",
        status="shipped",
        order_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderProOrderItem(
            order=order,
            product=product,
            orderpro_line_key=f"order-{product.id}:1",
            orderpro_product_id=product.orderpro_id,
            sku=product.orderpro_sku,
            quantity=qty_used,
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


def parse_csv_response(response) -> list[dict[str, str]]:
    assert response.content.startswith(b"\xef\xbb\xbf")
    text = response.content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


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


def test_export_purchase_order_csv_success(client, db_session):
    product, supplier, mapping = seed_product_supplier(
        db_session,
        supplier_name="CSV Supplier, Inc.",
        product_name='CSV "Quoted", Product',
    )
    product.orderpro_id = "4120"
    product.orderpro_sku = "CSV-SKU"
    product.barcode = "123456789"
    product.description = "Product description\nwith line break"
    product.category = "Export Category"
    product.current_stock = 12.5
    supplier.orderpro_code = "CSV-SUP"
    supplier.email = "orders@example.com"
    supplier.phone = "+123456"
    supplier.lead_time_days = 9
    db_session.commit()
    po = create_po(client, supplier.id)
    updated = add_line(client, po["id"], mapping.id, quantity=2.5)

    response = client.get(f"/purchase-orders/{updated['id']}/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment;" in response.headers["content-disposition"]
    assert f"purchase_order_{updated['id']}_CSV_Supplier_Inc_" in response.headers["content-disposition"]
    rows = parse_csv_response(response)
    assert len(rows) == 1
    row = rows[0]
    assert row["purchase_order_id"] == str(updated["id"])
    assert row["status"] == "draft"
    assert row["supplier_id"] == str(supplier.id)
    assert row["supplier_code"] == "CSV-SUP"
    assert row["supplier_name"] == "CSV Supplier, Inc."
    assert row["supplier_email"] == "orders@example.com"
    assert row["supplier_phone"] == "'+123456"
    assert row["supplier_lead_time_days"] == "9"
    assert row["product_id"] == str(product.id)
    assert row["orderpro_product_id"] == "4120"
    assert row["sku"] == "CSV-SKU"
    assert row["barcode"] == "123456789"
    assert row["product_name"] == 'CSV "Quoted", Product'
    assert row["product_description"] == "Product description\nwith line break"
    assert row["category"] == "Export Category"
    assert row["current_stock"] == "12.5"
    assert row["quantity"] == "2.5"
    assert row["unit_cost"] == "12.50"
    assert row["line_total"] == "31.25"
    assert row["order_total"] == "31.25"
    assert row["line_notes"] == "Line notes"
    assert row["minimum_order_quantity"] == "5"
    assert row["pack_size"] == "2"
    assert row["lead_time_days"] == "7"


def test_export_purchase_order_csv_multiple_lines_and_missing_optional_fields(client, db_session):
    _first_product, supplier, first_mapping = seed_product_supplier(db_session, supplier_name="Optional Supplier")
    second_product = Product(name="No Optional Fields", current_stock=0, supplier_id=supplier.id)
    db_session.add(second_product)
    db_session.flush()
    second_mapping = ProductSupplier(
        product_id=second_product.id,
        supplier_id=supplier.id,
        supplier_sku=None,
        supplier_product_name=None,
        purchase_price=None,
        currency=None,
        minimum_order_quantity=None,
        pack_size=None,
        lead_time_days=None,
        match_status="confirmed",
        match_method="manual",
    )
    db_session.add(second_mapping)
    db_session.commit()
    po = create_po(client, supplier.id)
    add_line(client, po["id"], first_mapping.id, quantity=1)
    add_line(client, po["id"], second_mapping.id, quantity=3)

    response = client.get(f"/purchase-orders/{po['id']}/export.csv")

    assert response.status_code == 200
    rows = parse_csv_response(response)
    assert len(rows) == 2
    second_row = rows[1]
    assert second_row["product_id"] == str(second_product.id)
    assert second_row["unit_cost"] == ""
    assert second_row["line_total"] == ""
    assert second_row["supplier_sku"] == ""
    assert second_row["supplier_product_name"] == ""
    assert second_row["product_description"] == ""


def test_export_purchase_order_csv_sanitizes_formula_injection(client, db_session):
    product, supplier, mapping = seed_product_supplier(
        db_session,
        supplier_name="=Danger Supplier",
        product_name="@Danger Product",
    )
    product.orderpro_sku = "+SKU"
    product.description = "-Description"
    mapping.supplier_sku = "=SUP-SKU"
    mapping.supplier_product_name = "+Supplier Product"
    db_session.commit()
    po = create_po(client, supplier.id)
    updated = add_line(client, po["id"], mapping.id, quantity=1)

    response = client.get(f"/purchase-orders/{updated['id']}/export.csv")

    assert response.status_code == 200
    row = parse_csv_response(response)[0]
    assert row["supplier_name"] == "'=Danger Supplier"
    assert row["product_name"] == "'@Danger Product"
    assert row["sku"] == "'+SKU"
    assert row["product_description"] == "'-Description"
    assert row["supplier_sku"] == "'=SUP-SKU"
    assert row["supplier_product_name"] == "'+Supplier Product"
    assert row["quantity"] == "1"
    assert row["unit_cost"] == "12.50"


def test_export_purchase_order_csv_unknown_id_returns_404(client):
    response = client.get("/purchase-orders/999999/export.csv")

    assert response.status_code == 404


def test_export_purchase_order_csv_empty_purchase_order_returns_400(client, db_session):
    _product, supplier, _mapping = seed_product_supplier(db_session, supplier_name="Empty Export Supplier")
    po = create_po(client, supplier.id)

    response = client.get(f"/purchase-orders/{po['id']}/export.csv")

    assert response.status_code == 400
    assert response.json()["detail"] == "Purchase order has no line items to export."


def test_export_purchase_order_csv_auth_enabled_requires_token(client, unauthenticated_client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    _product, supplier, mapping = seed_product_supplier(db_session, supplier_name="Auth Export Supplier")
    po = create_po(client, supplier.id)
    add_line(client, po["id"], mapping.id, quantity=2)
    unauthenticated_client.headers.pop("authorization", None)
    unauthenticated_client.headers.pop("Authorization", None)

    response = unauthenticated_client.get(f"/purchase-orders/{po['id']}/export.csv")

    assert response.status_code == 401


def test_export_purchase_order_csv_auth_disabled_allows_no_token(unauthenticated_client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    _product, supplier, mapping = seed_product_supplier(db_session, supplier_name="Disabled Auth Export Supplier")
    po = create_po(unauthenticated_client, supplier.id)
    add_line(unauthenticated_client, po["id"], mapping.id, quantity=2)

    response = unauthenticated_client.get(f"/purchase-orders/{po['id']}/export.csv")

    assert response.status_code == 200
    assert len(parse_csv_response(response)) == 1


def test_export_purchase_order_csv_valid_token_permits_export(client, db_session):
    _product, supplier, mapping = seed_product_supplier(db_session, supplier_name="Token Export Supplier")
    po = create_po(client, supplier.id)
    add_line(client, po["id"], mapping.id, quantity=2)

    response = client.get(f"/purchase-orders/{po['id']}/export.csv")

    assert response.status_code == 200


def test_export_purchase_order_csv_does_not_modify_purchase_order(client, db_session):
    _product, supplier, mapping = seed_product_supplier(db_session, supplier_name="Readonly Export Supplier")
    po = create_po(client, supplier.id)
    add_line(client, po["id"], mapping.id, quantity=2)
    before = db_session.get(PurchaseOrder, po["id"])
    before_state = {
        "status": before.status,
        "updated_at": before.updated_at,
        "total_amount": before.total_amount,
        "line_count": len(before.lines),
    }

    response = client.get(f"/purchase-orders/{po['id']}/export.csv")

    assert response.status_code == 200
    after = db_session.get(PurchaseOrder, po["id"])
    assert after.status == before_state["status"]
    assert after.updated_at == before_state["updated_at"]
    assert after.total_amount == before_state["total_amount"]
    assert len(after.lines) == before_state["line_count"]


def test_create_draft_po_from_one_valid_product(client, db_session):
    product, supplier, mapping = seed_draft_mapping(db_session)

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={
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
    assert len(payload["created_purchase_orders"]) == 1
    assert payload["summary"]["created_po_count"] == 1
    assert payload["summary"]["created_line_count"] == 1
    assert payload["summary"]["skipped_products"] == []
    line = po["lines"][0]
    assert line["product_id"] == product.id
    assert line["product_supplier_id"] is None
    assert line["supplier_sku"] == product.supplier_sku
    assert line["supplier_product_name"] == product.name
    assert line["unit_cost"] == product.cost_price
    assert line["currency"] is None
    assert line["lead_time_days"] == product.lead_time_days


def test_create_draft_po_from_products_groups_multiple_suppliers(client, db_session):
    product_a, supplier, _mapping_a = seed_draft_mapping(db_session, supplier_name="Multi Supplier")
    other_supplier = Supplier(name="Second Multi Supplier", normalized_name="SECOND MULTI SUPPLIER")
    product_b = Product(
        name="Second Draft Product",
        current_stock=1,
        supplier_record=other_supplier,
        supplier_sku="SECOND-SKU",
        cost_price=4.0,
    )
    db_session.add_all([other_supplier, product_b])
    db_session.flush()
    db_session.commit()

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={"product_ids": [product_a.id, product_b.id]},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["purchase_order"] is None
    assert payload["summary"]["created_po_count"] == 2
    assert payload["summary"]["created_line_count"] == 2
    assert {po["supplier_id"] for po in payload["created_purchase_orders"]} == {supplier.id, other_supplier.id}


def test_draft_po_from_products_skips_missing_mapping_and_returns_summary(client, db_session):
    valid_product, supplier, _mapping = seed_draft_mapping(db_session, supplier_name="Skip Supplier")
    unmapped_product = Product(name="Unmapped Draft Product", current_stock=1)
    db_session.add(unmapped_product)
    db_session.commit()

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={"product_ids": [valid_product.id, unmapped_product.id]},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["summary"]["created_line_count"] == 1
    assert payload["summary"]["skipped_products"] == [
        {
            "product_id": unmapped_product.id,
            "product_name": "Unmapped Draft Product",
            "reason": "Product is missing an OrderPro supplier mapping.",
        }
    ]


def test_draft_po_from_products_rejects_when_all_products_are_skipped(client, db_session):
    supplier = Supplier(name="No Lines Supplier", normalized_name="NO LINES SUPPLIER")
    product = Product(name="No Mapping Product", current_stock=1)
    db_session.add_all([supplier, product])
    db_session.commit()

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={"product_ids": [product.id]},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "No valid purchase order lines could be created."
    assert response.json()["detail"]["skipped_products"] == [
        {
            "product_id": product.id,
            "product_name": "No Mapping Product",
            "reason": "Product is missing an OrderPro supplier mapping.",
        }
    ]


def test_draft_po_from_products_skips_product_for_requested_different_supplier(client, db_session):
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
        "Product belongs to a different OrderPro supplier."
    )


def test_draft_po_from_products_does_not_require_product_supplier(client, db_session):
    product, supplier, _mapping = seed_draft_mapping(
        db_session,
        supplier_name="No Legacy Mapping Draft Supplier",
    )
    db_session.query(ProductSupplier).delete()
    db_session.commit()

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={"supplier_id": supplier.id, "product_ids": [product.id]},
    )

    assert response.status_code == 201
    line = response.json()["purchase_order"]["lines"][0]
    assert line["product_id"] == product.id
    assert line["product_supplier_id"] is None


def test_draft_po_from_products_respects_minimum_order_quantity(client, db_session):
    product, supplier, _mapping = seed_draft_mapping(
        db_session,
        supplier_name="MOQ Draft Supplier",
        product_overrides={"min_order_qty": 12},
    )

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={"supplier_id": supplier.id, "product_ids": [product.id]},
    )

    assert response.status_code == 201
    line = response.json()["purchase_order"]["lines"][0]
    assert line["quantity"] == 12
    assert line["minimum_order_quantity"] == 12


def test_draft_po_from_products_snapshots_product_fields_without_product_supplier_pack_size(client, db_session):
    product, supplier, _mapping = seed_draft_mapping(
        db_session,
        supplier_name="No Pack Draft Supplier",
        product_overrides={"min_order_qty": 5},
    )

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={"supplier_id": supplier.id, "product_ids": [product.id]},
    )

    assert response.status_code == 201
    line = response.json()["purchase_order"]["lines"][0]
    assert line["quantity"] == 5
    assert line["minimum_order_quantity"] == 5
    assert line["pack_size"] is None


def test_draft_po_from_products_uses_forecast_recommended_quantity_when_available(client, db_session):
    product, supplier, _mapping = seed_draft_mapping(
        db_session,
        supplier_name="Forecast Draft Supplier",
        product_overrides={"current_stock": 1, "safety_stock": 10, "lead_time_days": 4},
        mapping_overrides={
            "minimum_order_quantity": 1,
            "pack_size": 3,
            "lead_time_days": 4,
            "match_status": "matched",
        },
    )
    add_orderpro_demand_history(db_session, product, qty_used=2)

    response = client.post(
        "/purchase-orders/draft-from-products",
        json={"supplier_id": supplier.id, "product_ids": [product.id]},
    )

    assert response.status_code == 201
    line = response.json()["purchase_order"]["lines"][0]
    assert line["quantity"] == 17
    assert line["pack_size"] is None


def test_add_purchase_order_line_can_use_orderpro_product(client, db_session):
    product, supplier, _mapping = seed_draft_mapping(
        db_session,
        supplier_name="Product Line Supplier",
        product_overrides={"cost_price": 8.0, "min_order_qty": 3, "lead_time_days": 6},
    )
    po = create_po(client, supplier.id)

    response = client.post(
        f"/purchase-orders/{po['id']}/lines",
        json={"product_id": product.id, "quantity": 4, "notes": "OrderPro product line"},
    )

    assert response.status_code == 201
    line = response.json()["lines"][0]
    assert line["product_id"] == product.id
    assert line["product_supplier_id"] is None
    assert line["supplier_sku"] == product.supplier_sku
    assert line["supplier_product_name"] == product.name
    assert line["unit_cost"] == 8.0
    assert line["line_total"] == 32.0
    assert line["minimum_order_quantity"] == 3
    assert line["lead_time_days"] == 6


def test_add_purchase_order_line_rejects_orderpro_product_for_different_supplier(client, db_session):
    product, _supplier, _mapping = seed_draft_mapping(
        db_session,
        supplier_name="Original Product Supplier",
    )
    requested_supplier = Supplier(name="Line Requested Supplier", normalized_name="LINE REQUESTED SUPPLIER")
    db_session.add(requested_supplier)
    db_session.commit()
    po = create_po(client, requested_supplier.id)

    response = client.post(
        f"/purchase-orders/{po['id']}/lines",
        json={"product_id": product.id, "quantity": 1},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Product belongs to a different OrderPro supplier."


def test_supplier_forecast_returns_products_assigned_to_supplier(client, db_session):
    product, supplier, _mapping = seed_draft_mapping(
        db_session,
        supplier_name="Forecast Supplier Route",
        product_overrides={"current_stock": 1, "safety_stock": 10, "lead_time_days": 4},
    )
    other_supplier = Supplier(name="Other Forecast Supplier", normalized_name="OTHER FORECAST SUPPLIER")
    other_product = Product(name="Other Supplier Product", supplier_record=other_supplier, current_stock=1)
    db_session.add_all([other_supplier, other_product])
    db_session.commit()
    add_orderpro_demand_history(db_session, product, qty_used=2)

    response = client.get(f"/suppliers/{supplier.id}/forecast")

    assert response.status_code == 200
    payload = response.json()
    assert payload["supplier_id"] == supplier.id
    assert payload["product_count"] == 1
    assert [forecast["product_id"] for forecast in payload["forecasts"]] == [product.id]
    assert payload["forecasts"][0]["demand_source"] == "orderpro_orders"
    assert payload["products_needing_reorder"] == [product.id]
    assert payload["total_recommended_quantity"] == 17
    assert payload["total_estimated_cost"] == 170.0


def test_supplier_forecast_uses_open_demand_shortage(client, db_session):
    product, supplier, _mapping = seed_draft_mapping(
        db_session,
        supplier_name="Open Demand Forecast Supplier",
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    order = OrderProOrder(
        orderpro_id="open-supplier-forecast",
        order_number="SO-OPEN-SUPPLIER",
        status="confirmed",
        order_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderProOrderItem(
            order=order,
            product=product,
            orderpro_line_key="open-supplier-forecast:1",
            orderpro_product_id=product.orderpro_id,
            sku=product.orderpro_sku,
            quantity=0,
            quantity_ordered=64,
            quantity_shipped=0,
        )
    )
    db_session.commit()

    response = client.get(f"/suppliers/{supplier.id}/forecast")

    assert response.status_code == 200
    payload = response.json()
    forecast = payload["forecasts"][0]
    assert forecast["recommended_qty"] == 64
    assert forecast["recommended_action"] == "reorder"
    assert forecast["risk_level"] == "high"
    assert payload["products_needing_reorder"] == [product.id]
    assert payload["total_recommended_quantity"] == 64


def test_supplier_forecast_to_draft_creates_draft_for_reorder_products_only(client, db_session):
    reorder_product, supplier, _mapping = seed_draft_mapping(
        db_session,
        supplier_name="Supplier Forecast Draft",
        product_overrides={"current_stock": 1, "safety_stock": 10, "lead_time_days": 4},
    )
    monitor_product = Product(
        name="Monitor Product",
        supplier_record=supplier,
        current_stock=50,
        min_order_qty=1,
        cost_price=3.0,
    )
    db_session.add(monitor_product)
    db_session.commit()
    add_orderpro_demand_history(db_session, reorder_product, qty_used=2)

    response = client.post(
        f"/suppliers/{supplier.id}/draft-po-from-forecast",
        json={"created_by": "supplier-forecast", "notes": "Supplier forecast draft"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["summary"]["created_po_count"] == 1
    assert payload["summary"]["created_line_count"] == 1
    po = payload["purchase_order"]
    assert po["status"] == "draft"
    assert po["supplier_id"] == supplier.id
    assert [line["product_id"] for line in po["lines"]] == [reorder_product.id]
    assert po["approved_at"] is None
    assert po["issued_at"] is None


def test_supplier_forecast_to_draft_includes_open_demand_shortage_when_only_reorder_needed(client, db_session):
    product, supplier, _mapping = seed_draft_mapping(
        db_session,
        supplier_name="Open Demand Draft Supplier",
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    order = OrderProOrder(
        orderpro_id="open-draft-forecast",
        order_number="SO-OPEN-DRAFT",
        status="confirmed",
        order_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderProOrderItem(
            order=order,
            product=product,
            orderpro_line_key="open-draft-forecast:1",
            orderpro_product_id=product.orderpro_id,
            sku=product.orderpro_sku,
            quantity=0,
            quantity_ordered=64,
            quantity_shipped=0,
        )
    )
    db_session.commit()

    response = client.post(
        f"/suppliers/{supplier.id}/draft-po-from-forecast",
        json={
            "created_by": "supplier-forecast",
            "notes": "Supplier forecast draft",
            "only_reorder_needed": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["summary"]["created_po_count"] == 1
    assert payload["summary"]["created_line_count"] == 1
    assert payload["purchase_order"]["lines"][0]["product_id"] == product.id
    assert payload["purchase_order"]["lines"][0]["quantity"] == 64
