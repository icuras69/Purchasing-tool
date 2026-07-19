from datetime import date, datetime

from app.models.orderpro_order import OrderProOrder, OrderProOrderItem
from app.models.product import Product
from app.models.product_forecast_input_profile import ProductForecastInputProfile
from app.models.product_supplier import ProductSupplier
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.recommendation import Recommendation
from app.models.supplier import Supplier
from app.models.usage_history import UsageHistory


RECENT_DEMAND_DATE = date(2026, 7, 1)
STALE_DEMAND_DATE = date(2025, 1, 1)


def forbid_orderpro_calls(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Local purchase workflow smoke tests must not call OrderPro.")

    monkeypatch.setattr("app.services.orderpro_client.OrderProClient.generic_get", fail_if_called)


def seed_smoke_product(
    db_session,
    *,
    product_name: str,
    supplier_name: str = "Smoke Supplier",
    current_stock: float = 0,
    safety_stock: float = 6,
    min_order_qty: float = 1,
    cost_price: float | None = 5.0,
    lead_time_days: int | None = 4,
    supplier_lead_time_days: int | None = 4,
    source_system: str = "orderpro",
    is_non_inventory: bool = False,
) -> tuple[Product, Supplier, ProductSupplier]:
    supplier_display_name = f"{supplier_name} {product_name}"
    product = Product(
        name=product_name,
        orderpro_id=f"op-{product_name}",
        orderpro_sku=f"SKU-{product_name}",
        source_system=source_system,
        current_stock=current_stock,
        safety_stock=safety_stock,
        min_order_qty=min_order_qty,
        cost_price=cost_price,
        lead_time_days=lead_time_days,
        is_non_inventory=is_non_inventory,
    )
    supplier = Supplier(
        name=supplier_display_name,
        normalized_name=supplier_display_name.upper(),
        orderpro_id=f"supplier-{supplier_name}-{product_name}",
        orderpro_code=f"SUP-{supplier_name}-{product_name}",
        lead_time_days=supplier_lead_time_days,
    )
    db_session.add_all([product, supplier])
    db_session.flush()
    product.supplier_id = supplier.id
    product.supplier_sku = f"{supplier_name[:3].upper()}-SKU"
    mapping = ProductSupplier(
        product_id=product.id,
        supplier_id=supplier.id,
        supplier_sku=product.supplier_sku,
        supplier_product_name=supplier_display_name,
        purchase_price=cost_price,
        currency="USD",
        minimum_order_quantity=min_order_qty,
        pack_size=1,
        lead_time_days=lead_time_days,
        match_status="confirmed",
        match_method="smoke",
    )
    db_session.add(mapping)
    db_session.commit()
    return product, supplier, mapping


def add_usage(db_session, product: Product, *, demand_date: date, qty: float = 4) -> None:
    db_session.add(
        UsageHistory(
            product_id=product.id,
            date=demand_date,
            qty_used=qty,
            net_qty=qty,
            source_system="smoke",
        )
    )
    db_session.commit()


def add_orderpro_demand(db_session, product: Product, *, qty: float = 4) -> None:
    order = OrderProOrder(
        orderpro_id=f"smoke-order-{product.id}",
        order_number=f"SO-SMOKE-{product.id}",
        status="shipped",
        order_date=datetime(2026, 7, 1),
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderProOrderItem(
            order=order,
            product=product,
            orderpro_line_key=f"smoke-order-{product.id}:1",
            orderpro_product_id=product.orderpro_id,
            sku=product.orderpro_sku,
            quantity=qty,
            quantity_ordered=qty,
            quantity_shipped=qty,
        )
    )
    db_session.commit()


def add_forecast_profile(
    db_session,
    product: Product,
    *,
    cost_price: float | None = 5.0,
    lead_time_days: int | None = 4,
    pack_size: float | None = 1,
) -> None:
    now = datetime(2026, 7, 1)
    db_session.add(
        ProductForecastInputProfile(
            product_id=product.id,
            cost_price=cost_price,
            cost_source="product_record" if cost_price is not None else "missing",
            cost_confidence="high" if cost_price is not None else "missing",
            lead_time_days=lead_time_days,
            lead_time_source="supplier_record" if lead_time_days is not None else "missing",
            lead_time_confidence="high" if lead_time_days is not None else "missing",
            min_order_qty=product.min_order_qty,
            moq_source="product_record",
            pack_size=pack_size,
            pack_size_source="forecast_input_profile" if pack_size is not None else "missing",
            safety_stock=product.safety_stock,
            safety_stock_source="product_record",
            blocking_issues=[],
            warning_issues=[],
            readiness_score=100,
            calculation_version="smoke",
            calculated_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()


def create_manual_recommendation(
    db_session,
    product: Product,
    *,
    status: str = "accepted",
    recommendation_type: str = "reorder",
    quantity: float = 3,
    supplier_id: int | None = None,
    forecast_snapshot: dict | None = None,
) -> Recommendation:
    recommendation = Recommendation(
        product_id=product.id,
        supplier_id=product.supplier_id if supplier_id is None else supplier_id,
        recommended_qty=quantity,
        recommendation_type=recommendation_type,
        status=status,
        risk_level="medium",
        reason="Smoke test recommendation.",
        generated_by="smoke",
        estimated_unit_cost=product.cost_price,
        estimated_total_cost=round(quantity * product.cost_price, 2) if product.cost_price else None,
        forecast_snapshot=forecast_snapshot,
    )
    db_session.add(recommendation)
    db_session.commit()
    return recommendation


def create_po(client, supplier_id: int) -> dict:
    response = client.post(
        "/purchase-orders",
        json={"supplier_id": supplier_id, "notes": "Smoke draft", "created_by": "smoke"},
    )
    assert response.status_code == 201
    return response.json()


def add_legacy_line(client, po_id: int, mapping_id: int, *, quantity: float = 3) -> dict:
    response = client.post(
        f"/purchase-orders/{po_id}/lines",
        json={"product_supplier_id": mapping_id, "quantity": quantity, "notes": "Smoke line"},
    )
    assert response.status_code == 201
    return response.json()


def run_local_po_status_flow(client, po_id: int) -> dict:
    preflight = client.get(f"/purchase-orders/{po_id}/preflight")
    assert preflight.status_code == 200
    assert preflight.json()["can_submit"] is True

    submit = client.post(f"/purchase-orders/{po_id}/submit-for-approval")
    assert submit.status_code == 200
    assert submit.json()["status"] == "pending_approval"

    approve = client.post(f"/purchase-orders/{po_id}/approve", json={"approved_by": "manager"})
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    external_before_issue = client.get(f"/purchase-orders/{po_id}/external-send-readiness")
    assert external_before_issue.status_code == 200
    assert external_before_issue.json()["external_send_supported"] is False
    assert external_before_issue.json()["can_send_externally"] is False

    issue = client.post(f"/purchase-orders/{po_id}/issue")
    assert issue.status_code == 200
    assert issue.json()["status"] == "issued"
    assert issue.json()["issued_at"] is not None

    external_after_issue = client.get(f"/purchase-orders/{po_id}/external-send-readiness")
    assert external_after_issue.status_code == 200
    assert external_after_issue.json()["external_send_supported"] is False
    assert external_after_issue.json()["can_send_externally"] is False
    assert external_after_issue.json()["message"] == (
        "This purchase order is local-only. External OrderPro sending is not implemented yet."
    )
    return issue.json()


def test_smoke_recent_demand_recommendation_to_local_issued_po(client, db_session, monkeypatch):
    forbid_orderpro_calls(monkeypatch)
    product, supplier, _mapping = seed_smoke_product(
        db_session,
        product_name="Smoke Recent Demand Product",
        supplier_name="Smoke Recent Supplier",
    )
    add_orderpro_demand(db_session, product, qty=6)
    add_forecast_profile(db_session, product, pack_size=1)

    create_response = client.post(f"/recommendations/reorder/{product.id}")
    assert create_response.status_code == 201
    recommendation = create_response.json()
    assert recommendation["status"] == "pending_review"

    accept_response = client.post(
        f"/recommendations/{recommendation['id']}/accept",
        json={"reviewed_by": "manager"},
    )
    assert accept_response.status_code == 200
    assert accept_response.json()["status"] == "accepted"

    readiness = client.get(f"/recommendations/{recommendation['id']}/po-readiness")
    assert readiness.status_code == 200
    assert readiness.json()["can_create_draft_po"] is True
    assert readiness.json()["po_supplier_source"] == "products.supplier_id"

    convert = client.post(f"/recommendations/{recommendation['id']}/convert-to-draft-po")
    assert convert.status_code == 200
    converted = convert.json()
    po = converted["purchase_order"]
    assert po["status"] == "draft"
    assert po["supplier_id"] == supplier.id
    assert po["lines"][0]["product_id"] == product.id
    assert po["lines"][0]["product_supplier_id"] is None
    assert converted["recommendation"]["status"] == "converted_to_po"

    issued = run_local_po_status_flow(client, po["id"])
    assert issued["status"] == "issued"
    assert db_session.query(PurchaseOrder).count() == 1


def test_smoke_manager_approved_stale_demand_to_local_issued_po(client, db_session, monkeypatch):
    forbid_orderpro_calls(monkeypatch)
    product, supplier, _mapping = seed_smoke_product(
        db_session,
        product_name="Smoke Stale Demand Product",
        supplier_name="Smoke Stale Supplier",
        current_stock=0,
        safety_stock=0,
    )
    add_usage(db_session, product, demand_date=STALE_DEMAND_DATE, qty=4)
    add_forecast_profile(db_session, product, pack_size=1)

    blocked_recommendation = create_manual_recommendation(db_session, product, quantity=4)
    blocked_convert = client.post(f"/recommendations/{blocked_recommendation.id}/convert-to-draft-po")
    assert blocked_convert.status_code == 400
    assert "manager-approved one-time" in blocked_convert.json()["detail"]
    assert db_session.query(PurchaseOrder).count() == 0

    decision = client.post(
        f"/recommendations/stale-demand-review/{product.id}/decision",
        json={
            "decision": "manager_approved_one_time",
            "reviewed_by": "Maged",
            "notes": "Approved for one-time smoke test reorder.",
        },
    )
    assert decision.status_code == 200
    assert decision.json()["decision"] == "manager_approved_one_time"

    queue = client.get("/recommendations/manager-approved-stale-queue")
    assert queue.status_code == 200
    item = next(item for item in queue.json()["items"] if item["product_id"] == product.id)
    assert item["safety_status"] == "ready_for_manual_recommendation"

    create_review = client.post(
        f"/recommendations/manager-approved-stale-queue/{product.id}/create-review-recommendation",
        json={"created_by": "Maged"},
    )
    assert create_review.status_code == 200
    recommendation = create_review.json()
    assert recommendation["status"] == "pending_review"
    assert recommendation["forecast_snapshot"]["review_decision"] == "manager_approved_one_time"

    accept = client.post(
        f"/recommendations/{recommendation['id']}/accept",
        json={"reviewed_by": "Maged"},
    )
    assert accept.status_code == 200

    readiness = client.get(f"/recommendations/{recommendation['id']}/po-readiness")
    assert readiness.status_code == 200
    readiness_payload = readiness.json()
    assert readiness_payload["can_create_draft_po"] is True
    assert readiness_payload["required_manager_decision"] == "manager_approved_one_time"
    assert any("Stale-only demand" in warning for warning in readiness_payload["warnings"])

    convert = client.post(f"/recommendations/{recommendation['id']}/convert-to-draft-po")
    assert convert.status_code == 200
    po = convert.json()["purchase_order"]
    assert po["supplier_id"] == supplier.id

    preflight = client.get(f"/purchase-orders/{po['id']}/preflight")
    assert preflight.status_code == 200
    assert any("stale-demand recommendation" in warning for warning in preflight.json()["warnings"])

    issued = run_local_po_status_flow(client, po["id"])
    assert issued["status"] == "issued"


def test_smoke_recommendation_to_po_hard_blockers(client, db_session, monkeypatch):
    forbid_orderpro_calls(monkeypatch)

    legacy_product, _supplier, _mapping = seed_smoke_product(
        db_session,
        product_name="Smoke Legacy Only Product",
    )
    legacy_supplier_id = legacy_product.supplier_id
    legacy_product.supplier_id = None
    legacy_rec = create_manual_recommendation(
        db_session,
        legacy_product,
        supplier_id=legacy_supplier_id,
        quantity=3,
    )
    legacy_response = client.post(f"/recommendations/{legacy_rec.id}/convert-to-draft-po")
    assert legacy_response.status_code == 400
    assert "canonical supplier" in legacy_response.json()["detail"]

    lead_product, _supplier, _mapping = seed_smoke_product(
        db_session,
        product_name="Smoke Missing Lead Product",
        lead_time_days=None,
        supplier_lead_time_days=None,
    )
    add_usage(db_session, lead_product, demand_date=RECENT_DEMAND_DATE, qty=4)
    add_forecast_profile(db_session, lead_product, lead_time_days=None)
    lead_rec = create_manual_recommendation(db_session, lead_product, quantity=3)
    lead_response = client.post(f"/recommendations/{lead_rec.id}/convert-to-draft-po")
    assert lead_response.status_code == 400
    assert "lead time" in lead_response.json()["detail"].lower()

    qty_product, _supplier, _mapping = seed_smoke_product(
        db_session,
        product_name="Smoke Non Positive Quantity Product",
    )
    add_usage(db_session, qty_product, demand_date=RECENT_DEMAND_DATE, qty=4)
    qty_rec = create_manual_recommendation(db_session, qty_product, quantity=0)
    qty_response = client.post(f"/recommendations/{qty_rec.id}/convert-to-draft-po")
    assert qty_response.status_code == 400
    assert "greater than zero" in qty_response.json()["detail"]

    monitor_product, _supplier, _mapping = seed_smoke_product(
        db_session,
        product_name="Smoke Monitor Product",
        current_stock=100,
        safety_stock=0,
    )
    add_usage(db_session, monitor_product, demand_date=RECENT_DEMAND_DATE, qty=1)
    add_forecast_profile(db_session, monitor_product, pack_size=1)
    monitor_rec = create_manual_recommendation(db_session, monitor_product, quantity=1)
    monitor_response = client.post(f"/recommendations/{monitor_rec.id}/convert-to-draft-po")
    assert monitor_response.status_code == 400
    assert "Forecast action is not reorder" in monitor_response.json()["detail"]

    stale_product, _supplier, _mapping = seed_smoke_product(
        db_session,
        product_name="Smoke Unapproved Stale Product",
        current_stock=0,
        safety_stock=0,
    )
    add_usage(db_session, stale_product, demand_date=STALE_DEMAND_DATE, qty=4)
    stale_rec = create_manual_recommendation(db_session, stale_product, quantity=3)
    stale_response = client.post(f"/recommendations/{stale_rec.id}/convert-to-draft-po")
    assert stale_response.status_code == 400
    assert "manager-approved one-time" in stale_response.json()["detail"]


def test_smoke_po_preflight_blocks_bad_purchase_orders(client, db_session, monkeypatch):
    forbid_orderpro_calls(monkeypatch)
    product_a, supplier_a, mapping_a = seed_smoke_product(
        db_session,
        product_name="Smoke PO Product A",
        supplier_name="Smoke PO Supplier A",
    )
    product_b, _supplier_b, _mapping_b = seed_smoke_product(
        db_session,
        product_name="Smoke PO Product B",
        supplier_name="Smoke PO Supplier B",
    )

    empty_po = create_po(client, supplier_a.id)
    empty_submit = client.post(f"/purchase-orders/{empty_po['id']}/submit-for-approval")
    assert empty_submit.status_code == 400
    assert "Purchase order has no lines." in empty_submit.json()["detail"]

    mixed_po = create_po(client, supplier_a.id)
    add_legacy_line(client, mixed_po["id"], mapping_a.id, quantity=3)
    db_session.add(
        PurchaseOrderLine(
            purchase_order_id=mixed_po["id"],
            product_id=product_b.id,
            quantity=2,
            unit_cost=5,
        )
    )
    db_session.commit()
    mixed_submit = client.post(f"/purchase-orders/{mixed_po['id']}/submit-for-approval")
    assert mixed_submit.status_code == 400
    assert "multiple canonical suppliers" in mixed_submit.json()["detail"]

    invalid_po = create_po(client, supplier_a.id)
    payload = add_legacy_line(client, invalid_po["id"], mapping_a.id, quantity=3)
    line = db_session.get(PurchaseOrderLine, payload["lines"][0]["id"])
    line.quantity = 0
    db_session.commit()
    invalid_submit = client.post(f"/purchase-orders/{invalid_po['id']}/submit-for-approval")
    assert invalid_submit.status_code == 400
    assert "greater than zero" in invalid_submit.json()["detail"]

    valid_po = create_po(client, supplier_a.id)
    add_legacy_line(client, valid_po["id"], mapping_a.id, quantity=3)
    submit = client.post(f"/purchase-orders/{valid_po['id']}/submit-for-approval")
    assert submit.status_code == 200
    stored_line = db_session.query(PurchaseOrderLine).filter_by(purchase_order_id=valid_po["id"]).one()
    stored_line.quantity = 0
    db_session.commit()
    invalid_approve = client.post(f"/purchase-orders/{valid_po['id']}/approve")
    assert invalid_approve.status_code == 400
    assert "greater than zero" in invalid_approve.json()["detail"]

    assert product_a.id != product_b.id


def test_smoke_local_issue_never_enables_external_send(client, db_session, monkeypatch):
    forbid_orderpro_calls(monkeypatch)
    product, supplier, mapping = seed_smoke_product(
        db_session,
        product_name="Smoke Local Issue Boundary Product",
        supplier_name="Smoke Local Issue Supplier",
    )
    po = create_po(client, supplier.id)
    add_legacy_line(client, po["id"], mapping.id, quantity=3)

    submit = client.post(f"/purchase-orders/{po['id']}/submit-for-approval")
    assert submit.status_code == 200
    approve = client.post(f"/purchase-orders/{po['id']}/approve", json={"approved_by": "manager"})
    assert approve.status_code == 200
    issue = client.post(f"/purchase-orders/{po['id']}/issue")
    assert issue.status_code == 200
    assert issue.json()["status"] == "issued"

    readiness = client.get(f"/purchase-orders/{po['id']}/external-send-readiness")
    assert readiness.status_code == 200
    payload = readiness.json()
    assert payload["external_send_supported"] is False
    assert payload["can_send_externally"] is False
    assert payload["external_send_system"] == "OrderPro"
    assert payload["message"] == (
        "This purchase order is local-only. External OrderPro sending is not implemented yet."
    )
    assert db_session.query(PurchaseOrder).filter_by(id=po["id"], status="issued").count() == 1
    assert product.supplier_id == supplier.id
