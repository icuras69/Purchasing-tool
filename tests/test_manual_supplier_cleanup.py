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
