from datetime import datetime, timedelta

from app.models.orderpro_order import OrderProOrder, OrderProOrderItem
from app.models.orderpro_purchase_order import OrderProPurchaseOrder, OrderProPurchaseOrderLine
from app.models.product import Product
from app.models.product_supplier_assignment_review import ProductSupplierAssignmentReview
from app.models.supplier import Supplier
from app.models.usage_history import UsageHistory
from app.services.manual_supplier_cleanup import (
    apply_missing_supplier_cleanup_import,
    build_missing_supplier_cleanup_export,
    plan_missing_supplier_cleanup_import,
)
from app.core.security import settings
from app.services.seasonality_backtesting import audit_product_forecast_inputs


def _supplier(db_session, name="Cleanup Supplier", code="CLN", orderpro_id="sup-cleanup"):
    supplier = Supplier(
        name=name,
        normalized_name=name.lower().replace(" ", "-"),
        orderpro_code=code,
        orderpro_id=orderpro_id,
    )
    db_session.add(supplier)
    db_session.commit()
    return supplier


def _product(db_session, name="Cleanup Product", sku="CLEANUP-SKU", supplier_id=None, stock=0, cost=None):
    product = Product(
        name=name,
        source_system="orderpro",
        orderpro_id=f"op-{sku}",
        orderpro_sku=sku,
        supplier_id=supplier_id,
        current_stock=stock,
        cost_price=cost,
        lead_time_days=2,
        min_order_qty=1,
        is_active=True,
    )
    db_session.add(product)
    db_session.commit()
    return product


def _write_cleanup_csv(tmp_path, rows):
    path = tmp_path / "reviewed_cleanup.csv"
    headers = [
        "product_id",
        "product_name",
        "reviewed_supplier_id",
        "reviewed_supplier_code",
        "reviewed_supplier_name",
        "review_note",
    ]
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(str(row.get(header, "")) for header in headers))
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _add_open_customer_demand(db_session, product, quantity=6):
    order = OrderProOrder(
        orderpro_id=f"ord-{product.id}",
        status="confirmed",
        order_date=datetime.utcnow(),
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderProOrderItem(
            order_id=order.id,
            orderpro_line_key=f"line-{product.id}",
            product_id=product.id,
            quantity=quantity,
            quantity_ordered=quantity,
            quantity_shipped=0,
        )
    )
    db_session.commit()


def _add_shipped_demand(db_session, product, quantity=4):
    order = OrderProOrder(
        orderpro_id=f"ord-shipped-{product.id}",
        status="shipped",
        order_date=datetime.utcnow() - timedelta(days=5),
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderProOrderItem(
            order_id=order.id,
            orderpro_line_key=f"shipped-line-{product.id}",
            product_id=product.id,
            quantity=quantity,
            quantity_ordered=quantity,
            quantity_shipped=quantity,
        )
    )
    db_session.commit()


def _add_usage_history(db_session, product, quantity=4):
    db_session.add(
        UsageHistory(
            product_id=product.id,
            date=(datetime.utcnow() - timedelta(days=10)).date(),
            qty_used=quantity,
            net_qty=quantity,
            source_system="historical_sales_excel",
        )
    )
    db_session.commit()


def _add_orderpro_po_supplier_evidence(db_session, product, supplier):
    po = OrderProPurchaseOrder(
        orderpro_id=f"po-{product.id}",
        purchase_order_number=f"PO-{product.id}",
        supplier_id=supplier.id,
        orderpro_supplier_id=supplier.orderpro_id,
        supplier_code=supplier.orderpro_code,
        supplier_name=supplier.name,
        status="sent",
        order_date=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(po)
    db_session.flush()
    db_session.add(
        OrderProPurchaseOrderLine(
            orderpro_purchase_order_id=po.id,
            orderpro_line_id=f"pol-{product.id}",
            orderpro_line_key=f"pol-{product.id}",
            product_id=product.id,
            quantity_ordered=2,
            quantity_received=0,
            quantity_cancelled=0,
            quantity_open=2,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db_session.commit()


def test_export_includes_only_products_missing_supplier(db_session):
    supplier = _supplier(db_session)
    missing = _product(db_session, sku="MISSING")
    _product(db_session, sku="ASSIGNED", supplier_id=supplier.id)

    export = build_missing_supplier_cleanup_export(db_session)

    assert [row["product_id"] for row in export.rows] == [missing.id]
    assert export.summary["total_missing_supplier_products"] == 1


def test_priority_score_increases_for_open_demand_stock_and_history(db_session):
    product = _product(db_session, sku="PRIORITY", stock=5, cost=12.5)
    _add_open_customer_demand(db_session, product, quantity=8)
    _add_shipped_demand(db_session, product, quantity=3)

    export = build_missing_supplier_cleanup_export(db_session)
    row = export.rows[0]

    assert row["priority_score"] >= 95
    assert "open customer demand" in row["priority_reason"]
    assert "stock on hand" in row["priority_reason"]
    assert "demand history" in row["priority_reason"]
    assert export.summary["rows_with_open_customer_demand"] == 1
    assert export.summary["rows_with_stock"] == 1
    assert export.summary["rows_with_demand_history"] == 1


def test_export_includes_existing_suggestions_and_no_evidence_rows(db_session):
    supplier = _supplier(db_session)
    suggested = _product(db_session, sku="HAS-SUGGESTION")
    no_evidence = _product(db_session, sku="NO-EVIDENCE")
    _add_orderpro_po_supplier_evidence(db_session, suggested, supplier)

    export = build_missing_supplier_cleanup_export(db_session)

    rows = {row["product_id"]: row for row in export.rows}
    assert rows[suggested.id]["existing_suggested_supplier_id"] == supplier.id
    assert rows[no_evidence.id]["existing_confidence_label"] == "none"
    assert export.summary["rows_with_existing_suggestion"] == 1
    assert export.summary["no_evidence_rows"] == 1


def test_import_dry_run_writes_nothing(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session)
    path = _write_cleanup_csv(tmp_path, [{"product_id": product.id, "reviewed_supplier_id": supplier.id}])

    plan = plan_missing_supplier_cleanup_import(db_session, path)

    assert plan.summary["rows_confirmable"] == 1
    assert db_session.get(Product, product.id).supplier_id is None
    assert db_session.query(ProductSupplierAssignmentReview).count() == 0


def test_import_by_reviewed_supplier_id_confirms_local_supplier(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session)
    path = _write_cleanup_csv(tmp_path, [{"product_id": product.id, "reviewed_supplier_id": supplier.id, "review_note": "OK"}])

    plan = apply_missing_supplier_cleanup_import(db_session, path, reviewed_by="Maged")

    db_session.expire_all()
    review = db_session.query(ProductSupplierAssignmentReview).one()
    assert plan.products_confirmed == 1
    assert db_session.get(Product, product.id).supplier_id == supplier.id
    assert review.status == "confirmed"
    assert review.reviewed_by == "Maged"
    assert review.notes == "OK"
    assert review.evidence_summary["source"] == "manual_supplier_cleanup"


def test_import_by_reviewed_supplier_code_confirms_local_supplier(db_session, tmp_path):
    supplier = _supplier(db_session, code="CODEMATCH")
    product = _product(db_session)
    path = _write_cleanup_csv(tmp_path, [{"product_id": product.id, "reviewed_supplier_code": "codematch"}])

    plan = apply_missing_supplier_cleanup_import(db_session, path)

    assert plan.products_confirmed == 1
    assert db_session.get(Product, product.id).supplier_id == supplier.id


def test_import_by_unique_reviewed_supplier_name_confirms_local_supplier(db_session, tmp_path):
    supplier = _supplier(db_session, name="Unique Cleanup Name", code="UNIQUE")
    product = _product(db_session)
    path = _write_cleanup_csv(tmp_path, [{"product_id": product.id, "reviewed_supplier_name": "Unique Cleanup Name"}])

    plan = apply_missing_supplier_cleanup_import(db_session, path)

    assert plan.products_confirmed == 1
    assert db_session.get(Product, product.id).supplier_id == supplier.id


def test_ambiguous_supplier_name_is_skipped(db_session, tmp_path, monkeypatch):
    product = _product(db_session)
    path = _write_cleanup_csv(tmp_path, [{"product_id": product.id, "reviewed_supplier_name": "Ambiguous"}])

    def fake_lookup(_db):
        return {"by_id": {}, "by_code": {}, "unique_names": {}, "duplicate_names": {"ambiguous"}}

    monkeypatch.setattr("app.services.manual_supplier_cleanup._supplier_lookup", fake_lookup)
    plan = plan_missing_supplier_cleanup_import(db_session, path)

    assert plan.summary["rows_skipped_ambiguous_supplier_name"] == 1
    assert db_session.get(Product, product.id).supplier_id is None


def test_missing_supplier_input_and_supplier_not_found_are_skipped(db_session, tmp_path):
    product_one = _product(db_session, sku="NO-INPUT")
    product_two = _product(db_session, sku="NOT-FOUND")
    path = _write_cleanup_csv(
        tmp_path,
        [
            {"product_id": product_one.id},
            {"product_id": product_two.id, "reviewed_supplier_code": "UNKNOWN"},
        ],
    )

    plan = plan_missing_supplier_cleanup_import(db_session, path)

    assert plan.summary["rows_skipped_no_supplier_input"] == 1
    assert plan.summary["rows_skipped_supplier_not_found"] == 1


def test_existing_supplier_conflict_is_not_overwritten_and_same_supplier_is_idempotent(db_session, tmp_path):
    supplier = _supplier(db_session, name="Same Supplier", code="SAME")
    other = _supplier(db_session, name="Other Supplier", code="OTHER", orderpro_id="other")
    same_product = _product(db_session, sku="SAME-PRODUCT", supplier_id=supplier.id)
    conflict_product = _product(db_session, sku="CONFLICT-PRODUCT", supplier_id=other.id)
    path = _write_cleanup_csv(
        tmp_path,
        [
            {"product_id": same_product.id, "reviewed_supplier_id": supplier.id},
            {"product_id": conflict_product.id, "reviewed_supplier_id": supplier.id},
        ],
    )

    plan = apply_missing_supplier_cleanup_import(db_session, path)

    assert plan.products_confirmed == 0
    assert plan.summary["rows_skipped_already_has_supplier_same"] == 1
    assert plan.summary["rows_skipped_existing_supplier_conflict"] == 1
    assert db_session.get(Product, conflict_product.id).supplier_id == other.id


def test_apply_does_not_call_orderpro(db_session, tmp_path, monkeypatch):
    supplier = _supplier(db_session)
    product = _product(db_session)
    path = _write_cleanup_csv(tmp_path, [{"product_id": product.id, "reviewed_supplier_id": supplier.id}])

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("OrderPro client must not be used by manual supplier cleanup.")

    monkeypatch.setattr("app.services.orderpro_client.OrderProClient.generic_get", fail_if_called)
    plan = apply_missing_supplier_cleanup_import(db_session, path)

    assert plan.products_confirmed == 1


def test_forecast_readiness_improves_after_manual_cleanup_confirmation(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session)
    path = _write_cleanup_csv(tmp_path, [{"product_id": product.id, "reviewed_supplier_id": supplier.id}])

    before = audit_product_forecast_inputs(db_session, product)
    apply_missing_supplier_cleanup_import(db_session, path)
    db_session.expire_all()
    after = audit_product_forecast_inputs(db_session, db_session.get(Product, product.id))

    assert "missing_supplier" in before["blocking_issues"]
    assert "missing_supplier" not in after["blocking_issues"]


def test_cleanup_api_lists_missing_supplier_candidates(client, db_session):
    supplier = _supplier(db_session)
    missing = _product(db_session, sku="API-MISSING", stock=3, cost=10)
    _product(db_session, sku="API-ASSIGNED", supplier_id=supplier.id)

    response = client.get("/api/manual-supplier-cleanup/candidates")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["product_id"] == missing.id
    assert body["summary"]["total_missing_supplier"] == 1
    assert body["summary"]["with_stock"] == 1
    assert body["summary"]["with_cost"] == 1


def test_cleanup_api_priority_sorting_and_filters(client, db_session):
    low = _product(db_session, sku="LOW")
    high = _product(db_session, sku="HIGH", stock=4, cost=8)
    _add_open_customer_demand(db_session, high, quantity=9)

    response = client.get("/api/manual-supplier-cleanup/candidates?priority_only=true&has_open_demand=true")

    assert response.status_code == 200
    body = response.json()
    assert [item["product_id"] for item in body["items"]] == [high.id]
    assert low.id not in [item["product_id"] for item in body["items"]]


def test_cleanup_api_search_and_pagination(client, db_session):
    first = _product(db_session, name="Blue Training Halter", sku="BLUE-HALTER")
    _product(db_session, name="Red Training Halter", sku="RED-HALTER")

    response = client.get("/api/manual-supplier-cleanup/candidates?search=blue&page=1&page_size=1")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["total_pages"] == 1
    assert body["items"][0]["product_id"] == first.id


def test_cleanup_api_candidate_detail(client, db_session):
    product = _product(db_session, sku="DETAIL", stock=2, cost=6)

    response = client.get(f"/api/manual-supplier-cleanup/candidates/{product.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["product_id"] == product.id
    assert body["orderpro_sku"] == "DETAIL"
    assert body["description"] is None
    assert body["review"] is None


def test_cleanup_api_supplier_search_by_name_and_code(client, db_session):
    supplier = _supplier(db_session, name="Maged Supplies", code="MAGED")
    _supplier(db_session, name="Other Vendor", code="OTHER", orderpro_id="other-vendor")

    by_name = client.get("/api/manual-supplier-cleanup/suppliers?search=maged")
    by_code = client.get("/api/manual-supplier-cleanup/suppliers?search=MAGED")

    assert by_name.status_code == 200
    assert by_code.status_code == 200
    assert by_name.json()["items"][0]["id"] == supplier.id
    assert by_code.json()["items"][0]["orderpro_code"] == "MAGED"


def test_cleanup_api_successful_assignment_updates_product_and_review(client, db_session):
    supplier = _supplier(db_session)
    product = _product(db_session)

    response = client.post(
        f"/api/manual-supplier-cleanup/candidates/{product.id}/assign",
        json={"supplier_id": supplier.id, "reviewed_by": "Maged", "notes": "Confirmed locally"},
    )

    assert response.status_code == 200
    db_session.expire_all()
    review = db_session.query(ProductSupplierAssignmentReview).one()
    assert db_session.get(Product, product.id).supplier_id == supplier.id
    assert review.status == "confirmed"
    assert review.suggestion_source == "manual_supplier_cleanup"
    assert review.reviewed_by == "Maged"
    assert review.notes == "Confirmed locally"
    assert response.json()["review"]["status"] == "confirmed"


def test_cleanup_api_assignment_is_idempotent_for_same_supplier(client, db_session):
    supplier = _supplier(db_session)
    product = _product(db_session, supplier_id=supplier.id)

    response = client.post(
        f"/api/manual-supplier-cleanup/candidates/{product.id}/assign",
        json={"supplier_id": supplier.id, "reviewed_by": "Maged"},
    )

    assert response.status_code == 200
    assert db_session.get(Product, product.id).supplier_id == supplier.id


def test_cleanup_api_assignment_conflict_returns_409(client, db_session):
    existing = _supplier(db_session, name="Existing", code="EXIST", orderpro_id="exist")
    other = _supplier(db_session, name="Other", code="OTH", orderpro_id="oth")
    product = _product(db_session, supplier_id=existing.id)

    response = client.post(
        f"/api/manual-supplier-cleanup/candidates/{product.id}/assign",
        json={"supplier_id": other.id, "reviewed_by": "Maged"},
    )

    assert response.status_code == 409
    assert db_session.get(Product, product.id).supplier_id == existing.id


def test_cleanup_api_assignment_unknown_product_and_supplier(client, db_session):
    product = _product(db_session)

    missing_product = client.post(
        "/api/manual-supplier-cleanup/candidates/999999/assign",
        json={"supplier_id": 1},
    )
    missing_supplier = client.post(
        f"/api/manual-supplier-cleanup/candidates/{product.id}/assign",
        json={"supplier_id": 999999},
    )

    assert missing_product.status_code == 404
    assert missing_supplier.status_code == 404
    assert db_session.get(Product, product.id).supplier_id is None


def test_cleanup_api_deferred_review_does_not_assign_supplier(client, db_session):
    product = _product(db_session)

    response = client.post(
        f"/api/manual-supplier-cleanup/candidates/{product.id}/review",
        json={"status": "deferred", "reviewed_by": "Maged", "notes": "Need spreadsheet."},
    )

    assert response.status_code == 200
    db_session.expire_all()
    review = db_session.query(ProductSupplierAssignmentReview).one()
    assert db_session.get(Product, product.id).supplier_id is None
    assert review.status == "deferred"
    assert review.reviewed_by == "Maged"


def test_cleanup_api_summary_counts(client, db_session):
    supplier = _supplier(db_session)
    _product(db_session, sku="ASSIGNED-SUMMARY", supplier_id=supplier.id)
    missing = _product(db_session, sku="MISSING-SUMMARY", stock=2)
    client.post(
        f"/api/manual-supplier-cleanup/candidates/{missing.id}/review",
        json={"status": "rejected", "reviewed_by": "Maged"},
    )

    response = client.get("/api/manual-supplier-cleanup/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["total_products"] == 2
    assert body["products_with_supplier"] == 1
    assert body["products_missing_supplier"] == 1
    assert body["rejected_reviews"] == 1
    assert body["completion_percentage"] == 50.0


def test_cleanup_api_auth_disabled_allows_local_access(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)

    response = unauthenticated_client.get("/api/manual-supplier-cleanup/summary")

    assert response.status_code == 200


def test_cleanup_api_auth_enabled_requires_token(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    unauthenticated_client.headers.pop("authorization", None)
    unauthenticated_client.headers.pop("Authorization", None)

    response = unauthenticated_client.get("/api/manual-supplier-cleanup/summary")

    assert response.status_code == 401


def test_cleanup_api_does_not_call_orderpro(client, db_session, monkeypatch):
    supplier = _supplier(db_session)
    product = _product(db_session)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("OrderPro client must not be used by manual supplier cleanup API.")

    monkeypatch.setattr("app.services.orderpro_client.OrderProClient.generic_get", fail_if_called)
    response = client.post(
        f"/api/manual-supplier-cleanup/candidates/{product.id}/assign",
        json={"supplier_id": supplier.id},
    )

    assert response.status_code == 200
