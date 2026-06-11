from datetime import datetime, timedelta

from app.models.orderpro_purchase_order import OrderProPurchaseOrder, OrderProPurchaseOrderLine
from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.product_supplier_assignment_review import ProductSupplierAssignmentReview
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.supplier import Supplier
from app.services.forecasting import build_forecast
from app.services.seasonality_backtesting import audit_product_forecast_inputs
from app.services.supplier_assignment_review import (
    apply_supplier_assignment_suggestions,
    build_supplier_assignment_review_report,
)


def _supplier(db_session, name="Acme Supplier", orderpro_id="sup-1", orderpro_code="ACME"):
    supplier = Supplier(
        name=name,
        normalized_name=name.lower().replace(" ", "-"),
        orderpro_id=orderpro_id,
        orderpro_code=orderpro_code,
    )
    db_session.add(supplier)
    db_session.commit()
    return supplier


def _product(db_session, name="Missing Supplier Product", sku="SKU-1", supplier_id=None):
    product = Product(
        name=name,
        source_system="orderpro",
        orderpro_id=f"op-{sku}",
        orderpro_sku=sku,
        supplier_id=supplier_id,
        current_stock=5,
        lead_time_days=0,
        min_order_qty=1,
    )
    db_session.add(product)
    db_session.commit()
    return product


def _orderpro_po_evidence(db_session, product, supplier, *, count=1):
    now = datetime.utcnow()
    for index in range(count):
        po = OrderProPurchaseOrder(
            orderpro_id=f"op-po-{product.id}-{supplier.id}-{index}",
            purchase_order_number=f"PO-{index}",
            supplier_id=supplier.id,
            orderpro_supplier_id=supplier.orderpro_id,
            supplier_code=supplier.orderpro_code,
            supplier_name=supplier.name,
            status="sent",
            order_date=now - timedelta(days=index),
            raw_payload={},
            created_at=now,
            updated_at=now,
        )
        db_session.add(po)
        db_session.flush()
        db_session.add(
            OrderProPurchaseOrderLine(
                orderpro_purchase_order_id=po.id,
                orderpro_line_id=f"line-{supplier.id}-{index}",
                orderpro_line_key=f"line-{supplier.id}-{index}",
                product_id=product.id,
                orderpro_product_id=product.orderpro_id,
                sku=product.orderpro_sku,
                quantity_ordered=5,
                quantity_received=0,
                quantity_cancelled=0,
                quantity_open=5,
                unit_cost=10,
                raw_payload={},
                created_at=now,
                updated_at=now,
            )
        )
    db_session.commit()


def test_missing_supplier_product_appears_in_review_summary(db_session):
    _product(db_session)

    plan = build_supplier_assignment_review_report(db_session)

    assert plan.summary["missing_supplier_products"] == 1
    assert plan.items[0]["status"] == "no_evidence"


def test_product_with_supplier_id_is_excluded(db_session):
    supplier = _supplier(db_session)
    _product(db_session, supplier_id=supplier.id)

    plan = build_supplier_assignment_review_report(db_session)

    assert plan.summary["missing_supplier_products"] == 0


def test_repeated_orderpro_po_evidence_creates_high_confidence_suggestion(db_session):
    supplier = _supplier(db_session)
    product = _product(db_session)
    _orderpro_po_evidence(db_session, product, supplier, count=2)

    item = build_supplier_assignment_review_report(db_session).items[0]

    assert item["suggested_supplier_id"] == supplier.id
    assert item["confidence_label"] == "high"
    assert item["suggestion_source"] == "orderpro_purchase_orders_repeated"


def test_conflicting_po_supplier_evidence_lowers_confidence(db_session):
    supplier_one = _supplier(db_session, name="Supplier One", orderpro_id="1", orderpro_code="ONE")
    supplier_two = _supplier(db_session, name="Supplier Two", orderpro_id="2", orderpro_code="TWO")
    product = _product(db_session)
    _orderpro_po_evidence(db_session, product, supplier_one, count=1)
    _orderpro_po_evidence(db_session, product, supplier_two, count=1)

    item = build_supplier_assignment_review_report(db_session).items[0]

    assert item["confidence_label"] == "low"
    assert "Conflicting supplier evidence" in item["warnings"][0]


def test_legacy_product_supplier_is_low_confidence_evidence(db_session):
    supplier = _supplier(db_session)
    product = _product(db_session)
    db_session.add(
        ProductSupplier(
            product_id=product.id,
            supplier_id=supplier.id,
            supplier_sku="LEGACY-SKU",
            match_status="confirmed",
            match_method="legacy",
        )
    )
    db_session.commit()

    item = build_supplier_assignment_review_report(db_session).items[0]

    assert item["suggested_supplier_id"] == supplier.id
    assert item["confidence_label"] == "low"
    assert item["suggestion_source"] == "legacy_product_supplier"


def test_dry_run_writes_nothing(db_session):
    supplier = _supplier(db_session)
    product = _product(db_session)
    _orderpro_po_evidence(db_session, product, supplier, count=2)

    build_supplier_assignment_review_report(db_session)

    assert db_session.query(ProductSupplierAssignmentReview).count() == 0
    assert db_session.get(Product, product.id).supplier_id is None


def test_apply_suggestions_creates_review_records_only(db_session):
    supplier = _supplier(db_session)
    product = _product(db_session)
    _orderpro_po_evidence(db_session, product, supplier, count=2)

    plan = apply_supplier_assignment_suggestions(db_session)

    review = db_session.query(ProductSupplierAssignmentReview).one()
    assert plan.records_created == 1
    assert review.suggested_supplier_id == supplier.id
    assert review.status == "suggested"
    assert db_session.get(Product, product.id).supplier_id is None


def test_confirm_high_confidence_requires_explicit_flag(db_session):
    supplier = _supplier(db_session)
    product = _product(db_session)
    _orderpro_po_evidence(db_session, product, supplier, count=2)

    apply_supplier_assignment_suggestions(db_session)
    assert db_session.get(Product, product.id).supplier_id is None

    apply_supplier_assignment_suggestions(db_session, confirm_high_confidence=True)
    assert db_session.get(Product, product.id).supplier_id == supplier.id


def test_confirm_endpoint_updates_product_supplier_locally(client, db_session):
    supplier = _supplier(db_session)
    product = _product(db_session)

    response = client.post(
        f"/products/{product.id}/supplier-assignment-review/confirm",
        json={"supplier_id": supplier.id, "reviewed_by": "tester", "note": "Confirmed locally"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    db_session.expire_all()
    assert db_session.get(Product, product.id).supplier_id == supplier.id


def test_confirm_endpoint_does_not_call_orderpro(client, db_session, monkeypatch):
    supplier = _supplier(db_session)
    product = _product(db_session)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("OrderPro client must not be called by local supplier confirmation.")

    monkeypatch.setattr("app.services.orderpro_client.OrderProClient.generic_get", fail_if_called)
    response = client.post(
        f"/products/{product.id}/supplier-assignment-review/confirm",
        json={"supplier_id": supplier.id},
    )

    assert response.status_code == 200


def test_confirm_endpoint_validates_supplier_exists(client, db_session):
    product = _product(db_session)

    response = client.post(
        f"/products/{product.id}/supplier-assignment-review/confirm",
        json={"supplier_id": 999999},
    )

    assert response.status_code == 404
    assert db_session.get(Product, product.id).supplier_id is None


def test_reject_endpoint_does_not_change_product_supplier(client, db_session):
    product = _product(db_session)

    response = client.post(
        f"/products/{product.id}/supplier-assignment-review/reject",
        json={"reason": "Wrong supplier", "reviewed_by": "tester"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    db_session.expire_all()
    assert db_session.get(Product, product.id).supplier_id is None


def test_unconfirmed_suggestion_does_not_affect_forecast_supplier_context(db_session):
    supplier = _supplier(db_session)
    product = _product(db_session)
    _orderpro_po_evidence(db_session, product, supplier, count=2)

    forecast = build_forecast(db_session, product)

    assert forecast["supplier_context"]["mapping_source"] == "missing"
    assert forecast["supplier_context"]["needs_supplier_mapping"] is True


def test_confirmed_supplier_affects_forecast_supplier_context(client, db_session):
    supplier = _supplier(db_session)
    product = _product(db_session)

    client.post(
        f"/products/{product.id}/supplier-assignment-review/confirm",
        json={"supplier_id": supplier.id},
    )

    db_session.expire_all()
    forecast = build_forecast(db_session, db_session.get(Product, product.id))
    assert forecast["supplier_context"]["mapping_source"] == "orderpro_product_supplier"
    assert forecast["supplier_context"]["supplier_id"] == supplier.id


def test_forecast_readiness_shows_suggestion_but_remains_blocking(db_session):
    supplier = _supplier(db_session)
    product = _product(db_session)
    _orderpro_po_evidence(db_session, product, supplier, count=2)

    audit = audit_product_forecast_inputs(db_session, product)

    assert "missing_supplier" in audit["blocking_issues"]
    assert audit["supplier_assignment_suggestion"]["suggested_supplier_id"] == supplier.id


def test_forecast_readiness_improves_after_confirmation(client, db_session):
    supplier = _supplier(db_session)
    product = _product(db_session)

    before = audit_product_forecast_inputs(db_session, product)
    client.post(
        f"/products/{product.id}/supplier-assignment-review/confirm",
        json={"supplier_id": supplier.id},
    )
    db_session.expire_all()
    after = audit_product_forecast_inputs(db_session, db_session.get(Product, product.id))

    assert "missing_supplier" in before["blocking_issues"]
    assert "missing_supplier" not in after["blocking_issues"]


def test_supplier_list_endpoint_returns_read_only_supplier_options(client, db_session):
    supplier = _supplier(db_session)

    response = client.get("/suppliers")

    assert response.status_code == 200
    assert response.json()[0]["id"] == supplier.id
