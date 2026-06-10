from datetime import date, datetime

from app.models.orderpro_purchase_order import OrderProPurchaseOrder, OrderProPurchaseOrderLine
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.supplier import Supplier
from app.services.forecasting import build_forecast
from app.services.inbound_stock import get_product_inbound_stock
from app.services.orderpro_client import OrderProClient, extract_records
from app.services.orderpro_purchase_order_sync import (
    apply_orderpro_purchase_order_sync,
    extract_purchase_order_items,
    is_open_orderpro_purchase_order_status,
    parse_purchase_order_line_quantities,
    plan_orderpro_purchase_order_sync,
    resolve_purchase_order_product,
    resolve_purchase_order_supplier,
)
from app.services.purchase_order_drafting import DraftPurchaseOrderError, build_supplier_forecast, create_draft_po_from_supplier_forecast
import scripts.sync_orderpro_purchase_orders as sync_po_script


def supplier(name: str = "Supplier", **overrides) -> Supplier:
    defaults = {
        "name": name,
        "normalized_name": name.lower().replace(" ", "-"),
    }
    defaults.update(overrides)
    return Supplier(**defaults)


def product(name: str = "Product", **overrides) -> Product:
    defaults = {
        "name": name,
        "current_stock": 0,
        "min_order_qty": 1,
        "safety_stock": 0,
        "lead_time_days": 0,
        "source_system": "orderpro",
    }
    defaults.update(overrides)
    return Product(**defaults)


def po_payload(**overrides):
    payload = {
        "id": 9001,
        "po_number": "PO-9001",
        "status": "sent",
        "supplier": {"id": 77, "code": "SUP77", "name": "OrderPro Supplier"},
        "order_date": "2026-06-01T00:00:00Z",
        "expected_date": "2026-06-20T00:00:00Z",
        "items": [
            {
                "id": 1,
                "product_id": 100,
                "sku": "SKU-100",
                "name": "OrderPro Product",
                "qty": "5.000",
                "qty_received": "4.000",
                "unit_cost": "2.50",
                "total": "12.50",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_purchase_order_payload_parser_handles_nested_paginator():
    payload = {"data": {"current_page": 1, "data": [po_payload()]}}
    items_payload = {"items": {"data": [{"id": 1, "sku": "SKU"}]}}

    assert len(extract_records(payload)) == 1
    assert extract_purchase_order_items(items_payload)[0]["sku"] == "SKU"


def test_orderpro_client_has_no_write_methods_for_po_mirror_task():
    assert not hasattr(OrderProClient, "post")
    assert not hasattr(OrderProClient, "patch")
    assert not hasattr(OrderProClient, "delete")


def test_status_mapping_includes_open_and_excludes_terminal_statuses():
    for status in ["sent", "partial", "partially received"]:
        assert is_open_orderpro_purchase_order_status(status)

    for status in ["approved", "issued", "open", "cancelled", "closed", "received", "fully_received", "draft", "rejected"]:
        assert not is_open_orderpro_purchase_order_status(status)


def test_quantity_parser_maps_orderpro_qty_fields_without_cancelled_warning_spam():
    ordered, received, cancelled, open_qty, warnings = parse_purchase_order_line_quantities(
        {"qty": "3.000", "qty_received": "7.000", "unit_cost": "2.50"}
    )
    assert ordered == 10.0
    assert received == 7.0
    assert cancelled == 0.0
    assert open_qty == 3.0
    assert warnings == []

    *_values, fallback_open_qty, fallback_warnings = parse_purchase_order_line_quantities({"qty_ordered": "5"})
    assert fallback_open_qty == 5.0
    assert fallback_warnings == ["missing_received_quantity_fallback"]


def test_received_sent_partial_and_draft_quantity_policy(db_session):
    supplier_obj = supplier("OrderPro Supplier", orderpro_id="77", orderpro_code="SUP77")
    product_obj = product("OrderPro Product", orderpro_id="100", orderpro_sku="SKU-100")
    db_session.add_all([supplier_obj, product_obj])
    db_session.flush()
    received = po_payload(id=1, status="received", items=[{**po_payload()["items"][0], "id": 1, "qty": "0", "qty_received": "8"}])
    sent = po_payload(id=2, status="sent", items=[{**po_payload()["items"][0], "id": 2, "qty": "10", "qty_received": "0"}])
    partial = po_payload(id=3, status="partial", items=[{**po_payload()["items"][0], "id": 3, "qty": "3", "qty_received": "7"}])
    draft = po_payload(id=4, status="draft", items=[{**po_payload()["items"][0], "id": 4, "qty": "11", "qty_received": "0"}])

    report = plan_orderpro_purchase_order_sync(db_session, [received, sent, partial, draft])
    apply_orderpro_purchase_order_sync(db_session, [received, sent, partial, draft], synced_at=datetime(2026, 6, 1))
    db_session.flush()
    inbound = get_product_inbound_stock(db_session, product_obj.id)

    lines = {line.orderpro_line_id: line for line in db_session.query(OrderProPurchaseOrderLine).all()}
    assert lines["1"].quantity_open == 0
    assert lines["1"].quantity_received == 8
    assert lines["1"].quantity_ordered == 8
    assert lines["2"].quantity_open == 10
    assert lines["2"].quantity_ordered == 10
    assert lines["3"].quantity_open == 3
    assert lines["3"].quantity_received == 7
    assert lines["3"].quantity_ordered == 10
    assert inbound["incoming_qty_orderpro"] == 13
    assert report["summary"]["included_open_quantity_total"] == 13
    assert report["summary"]["open_quantity_by_status"]["sent"] == 10
    assert report["summary"]["open_quantity_by_status"]["partial"] == 3
    assert report["summary"]["excluded_quantity_by_status"]["draft"] == 11
    assert report["summary"]["warning_counts_by_type"] == {}
    assert report["report_notes"] == ["OrderPro does not expose cancelled quantity in sampled lines; using 0."]
    assert report["sample_received_lines"][0]["qty"] == "0"
    assert report["sample_received_lines"][0]["qty_received"] == "8"


def test_product_and_supplier_linking_methods_are_deterministic(db_session):
    supplier_obj = supplier("OrderPro Supplier", orderpro_id="77", orderpro_code="SUP77")
    by_name_supplier = supplier("Unique Name Supplier")
    product_by_id = product("By ID", orderpro_id="100", orderpro_sku="SKU-100", barcode="B100")
    product_by_sku = product("By SKU", orderpro_id="101", orderpro_sku="SKU-101", barcode="B101")
    product_by_barcode = product("By Barcode", orderpro_id="102", orderpro_sku="SKU-102", barcode="B102")
    duplicate_barcode_a = product("Duplicate A", orderpro_id="103", orderpro_sku="SKU-103", barcode="DUP")
    duplicate_barcode_b = product("Duplicate B", orderpro_id="104", orderpro_sku="SKU-104", barcode="DUP")
    db_session.add_all(
        [supplier_obj, by_name_supplier, product_by_id, product_by_sku, product_by_barcode, duplicate_barcode_a, duplicate_barcode_b]
    )
    db_session.flush()

    product_by_orderpro_id = {"100": product_by_id}
    product_by_sku = {"SKU-101": product_by_sku}
    product_by_unique_barcode = {"B102": product_by_barcode}
    ambiguous_barcodes = {"DUP"}

    assert resolve_purchase_order_product(
        {"product_id": "100"},
        product_by_orderpro_id=product_by_orderpro_id,
        product_by_sku=product_by_sku,
        product_by_unique_barcode=product_by_unique_barcode,
        ambiguous_barcodes=ambiguous_barcodes,
    ) == (product_by_id, "orderpro_product_id")
    assert resolve_purchase_order_product(
        {"sku": "SKU-101"},
        product_by_orderpro_id=product_by_orderpro_id,
        product_by_sku=product_by_sku,
        product_by_unique_barcode=product_by_unique_barcode,
        ambiguous_barcodes=ambiguous_barcodes,
    ) == (product_by_sku["SKU-101"], "sku")
    assert resolve_purchase_order_product(
        {"barcode": "B102"},
        product_by_orderpro_id=product_by_orderpro_id,
        product_by_sku=product_by_sku,
        product_by_unique_barcode=product_by_unique_barcode,
        ambiguous_barcodes=ambiguous_barcodes,
    ) == (product_by_barcode, "barcode")
    assert resolve_purchase_order_product(
        {"barcode": "DUP"},
        product_by_orderpro_id=product_by_orderpro_id,
        product_by_sku=product_by_sku,
        product_by_unique_barcode=product_by_unique_barcode,
        ambiguous_barcodes=ambiguous_barcodes,
    ) == (None, "ambiguous_barcode")

    assert resolve_purchase_order_supplier(
        {"supplier_id": "77"},
        supplier_by_orderpro_id={"77": supplier_obj},
        supplier_by_code={},
        supplier_by_unique_name={},
    ) == (supplier_obj, "orderpro_supplier_id")
    assert resolve_purchase_order_supplier(
        {"supplier": {"code": "SUP77"}},
        supplier_by_orderpro_id={},
        supplier_by_code={"SUP77": supplier_obj},
        supplier_by_unique_name={},
    ) == (supplier_obj, "supplier_code")
    assert resolve_purchase_order_supplier(
        {"supplier": {"name": "Unique Name Supplier"}},
        supplier_by_orderpro_id={},
        supplier_by_code={},
        supplier_by_unique_name={"unique name supplier": by_name_supplier},
    ) == (by_name_supplier, "supplier_name")


def test_orderpro_purchase_order_apply_is_idempotent_and_updates_lines(db_session):
    supplier_obj = supplier("OrderPro Supplier", orderpro_id="77", orderpro_code="SUP77")
    product_obj = product("OrderPro Product", orderpro_id="100", orderpro_sku="SKU-100")
    db_session.add_all([supplier_obj, product_obj])
    db_session.flush()

    first = apply_orderpro_purchase_order_sync(db_session, [po_payload()], synced_at=datetime(2026, 6, 1))
    db_session.flush()
    second = apply_orderpro_purchase_order_sync(db_session, [po_payload()], synced_at=datetime(2026, 6, 1))
    db_session.flush()
    changed_payload = po_payload(items=[{**po_payload()["items"][0], "qty": "4.000", "qty_received": "5.000"}])
    third = apply_orderpro_purchase_order_sync(db_session, [changed_payload], synced_at=datetime(2026, 6, 2))
    db_session.flush()

    assert first["summary"]["purchase_orders_created"] == 1
    assert first["summary"]["purchase_order_lines_created"] == 1
    assert second["summary"]["purchase_orders_unchanged"] == 1
    assert second["summary"]["purchase_order_lines_unchanged"] == 1
    assert third["summary"]["purchase_order_lines_updated"] == 1
    assert db_session.query(OrderProPurchaseOrder).count() == 1
    assert db_session.query(OrderProPurchaseOrderLine).count() == 1
    line = db_session.query(OrderProPurchaseOrderLine).one()
    assert line.product_id == product_obj.id
    assert line.quantity_open == 4.0
    assert line.quantity_received == 5.0
    assert line.quantity_ordered == 9.0
    assert line.unit_cost == 2.5


def test_dry_run_reports_linking_quantity_and_does_not_write(db_session):
    supplier_obj = supplier("OrderPro Supplier", orderpro_id="77", orderpro_code="SUP77")
    product_obj = product("OrderPro Product", orderpro_id="100", orderpro_sku="SKU-100")
    db_session.add_all([supplier_obj, product_obj])
    db_session.flush()

    report = plan_orderpro_purchase_order_sync(db_session, [po_payload()])

    assert report["summary"]["purchase_orders_to_create"] == 1
    assert report["summary"]["purchase_order_lines_to_create"] == 1
    assert report["summary"]["product_link_methods"] == {"orderpro_product_id": 1}
    assert report["summary"]["supplier_link_methods"] == {"orderpro_supplier_id": 1}
    assert report["summary"]["open_quantity_total"] == 5.0
    assert report["summary"]["quantity_field_coverage"]["qty_present_count"] == 1
    assert report["summary"]["quantity_field_coverage"]["qty_received_present_count"] == 1
    assert report["summary"]["quantity_field_coverage"]["unit_cost_present_count"] == 1
    assert report["summary"]["warning_counts_by_type"] == {}
    assert db_session.query(OrderProPurchaseOrder).count() == 0


def test_sample_saving_writes_one_sanitized_file_per_status(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_po_script, "PROJECT_ROOT", tmp_path)
    rows = [
        po_payload(id=1, status="received", items=[{**po_payload()["items"][0], "qty": "0", "qty_received": "8"}]),
        po_payload(id=2, status="draft"),
        po_payload(id=3, status="sent"),
        po_payload(id=4, status="partial"),
        po_payload(id=5, status="custom-review", token="secret-value"),
    ]

    paths = sync_po_script.save_samples_by_status(rows)

    assert set(paths) == {"received", "draft", "sent", "partial", "custom_review"}
    for path in paths.values():
        text = path.read_text(encoding="utf-8")
        assert "secret-value" not in text
        assert "_sample_summary" in text
        assert "quantity_fields" in text


def test_inbound_stock_combines_local_and_orderpro_sources(client, db_session):
    supplier_obj = supplier("Inbound Supplier", orderpro_id="77", orderpro_code="SUP77")
    product_obj = product(
        "Inbound Product",
        orderpro_id="100",
        orderpro_sku="SKU-100",
        supplier_record=supplier_obj,
        current_stock=0,
        cost_price=2,
    )
    db_session.add_all([supplier_obj, product_obj])
    db_session.flush()
    local_po = PurchaseOrder(supplier=supplier_obj, status="approved", delivery_date=date(2026, 6, 20), created_by="test")
    db_session.add(local_po)
    db_session.flush()
    db_session.add(
        PurchaseOrderLine(
            purchase_order=local_po,
            product=product_obj,
            quantity=5,
            unit_cost=2,
            line_total=10,
        )
    )
    apply_orderpro_purchase_order_sync(db_session, [po_payload()], synced_at=datetime(2026, 6, 1))
    db_session.commit()

    inbound = get_product_inbound_stock(db_session, product_obj.id)
    detail = client.get(f"/products/{product_obj.id}/inbound-stock")
    summary = client.get("/inbound-stock/summary")

    assert inbound["incoming_qty"] == 10.0
    assert inbound["incoming_qty_local"] == 5.0
    assert inbound["incoming_qty_orderpro"] == 5.0
    assert inbound["source_breakdown"]["orderpro_purchase_orders"]["incoming_qty"] == 5.0
    assert detail.status_code == 200
    assert detail.json()["incoming_qty_orderpro"] == 5.0
    assert summary.status_code == 200
    assert summary.json()["products_with_orderpro_inbound"] == 1
    assert summary.json()["total_orderpro_inbound_units"] == 5.0


def test_orderpro_inbound_reduces_forecast_recommendation(db_session):
    supplier_obj = supplier("Forecast Supplier", orderpro_id="77", orderpro_code="SUP77", lead_time_days=0)
    product_obj = product(
        "Forecast Product",
        orderpro_id="100",
        orderpro_sku="SKU-100",
        supplier_record=supplier_obj,
        current_stock=0,
        cost_price=2,
    )
    db_session.add_all([supplier_obj, product_obj])
    db_session.flush()
    from app.models.orderpro_order import OrderProOrder, OrderProOrderItem

    order = OrderProOrder(orderpro_id="SO-1", order_number="SO-1", status="confirmed")
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderProOrderItem(
            order=order,
            product=product_obj,
            orderpro_line_key="SO-1:1",
            orderpro_product_id="100",
            sku="SKU-100",
            quantity=0,
            quantity_ordered=64,
            quantity_shipped=0,
        )
    )
    apply_orderpro_purchase_order_sync(
        db_session,
        [po_payload(items=[{**po_payload()["items"][0], "qty": "20.000", "qty_received": "0.000"}])],
        synced_at=datetime(2026, 6, 1),
    )
    db_session.commit()

    forecast = build_forecast(db_session, product_obj)

    assert forecast["recommended_qty_before_inbound"] == 64
    assert forecast["incoming_qty"] == 20
    assert forecast["recommended_qty_after_inbound"] == 44
    assert forecast["recommended_qty"] == 44


def test_supplier_forecast_and_draft_po_use_orderpro_inbound_quantity(db_session):
    supplier_obj = supplier("Supplier Forecast Supplier", orderpro_id="77", orderpro_code="SUP77", lead_time_days=0)
    product_obj = product(
        "Supplier Forecast Product",
        orderpro_id="100",
        orderpro_sku="SKU-100",
        supplier_record=supplier_obj,
        current_stock=0,
        cost_price=2,
    )
    db_session.add_all([supplier_obj, product_obj])
    db_session.flush()
    from app.models.orderpro_order import OrderProOrder, OrderProOrderItem

    order = OrderProOrder(orderpro_id="SO-2", order_number="SO-2", status="confirmed")
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderProOrderItem(
            order=order,
            product=product_obj,
            orderpro_line_key="SO-2:1",
            orderpro_product_id="100",
            sku="SKU-100",
            quantity=0,
            quantity_ordered=64,
            quantity_shipped=0,
        )
    )
    apply_orderpro_purchase_order_sync(
        db_session,
        [po_payload(items=[{**po_payload()["items"][0], "qty": "64.000", "qty_received": "0.000"}])],
        synced_at=datetime(2026, 6, 1),
    )
    db_session.commit()

    supplier_forecast = build_supplier_forecast(db_session, supplier_obj.id)

    assert supplier_forecast["forecasts"][0]["incoming_qty"] == 64
    assert supplier_forecast["forecasts"][0]["recommended_qty"] == 0
    try:
        create_draft_po_from_supplier_forecast(db_session, supplier_id=supplier_obj.id, only_reorder_needed=True)
    except DraftPurchaseOrderError as error:
        assert error.message == "No products need reorder for this supplier."
    else:
        raise AssertionError("Supplier draft PO should not include products covered by OrderPro inbound stock.")
