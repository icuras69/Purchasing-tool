from datetime import datetime, timedelta, timezone

from app.models.orderpro_order import OrderProOrder, OrderProOrderItem
from app.models.orderpro_purchase_order import OrderProPurchaseOrder, OrderProPurchaseOrderLine
from app.models.product import Product
from app.models.product_forecast_input_profile import ProductForecastInputProfile
from app.models.product_supplier_assignment_review import ProductSupplierAssignmentReview
from app.models.product_supplier import ProductSupplier
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.supplier import Supplier
from app.services.forecast_input_reconciliation import (
    apply_forecast_input_reconciliation,
    evaluate_product_readiness,
    effective_forecast_inputs,
    forecast_input_audit,
    plan_forecast_input_reconciliation,
    profile_or_effective_inputs,
)
from app.core.security import settings
from app.services.forecasting import build_forecast


def make_supplier(db_session, name: str = "Input Supplier", **overrides) -> Supplier:
    defaults = {
        "name": name,
        "normalized_name": name.lower(),
        "source_system": "orderpro",
    }
    defaults.update(overrides)
    supplier = Supplier(**defaults)
    db_session.add(supplier)
    db_session.flush()
    return supplier


def make_orderpro_product(db_session, **overrides) -> Product:
    defaults = {
        "name": "Input Product",
        "source_system": "orderpro",
        "orderpro_id": "OP-INPUT",
        "orderpro_sku": "OP-INPUT-SKU",
        "current_stock": 0,
        "min_order_qty": 0,
        "lead_time_days": 0,
        "safety_stock": 0,
        "cost_price": None,
    }
    defaults.update(overrides)
    product = Product(**defaults)
    db_session.add(product)
    db_session.flush()
    return product


def add_orderpro_po_cost(
    db_session,
    product: Product,
    unit_cost: float,
    *,
    days_ago: int = 0,
    status: str = "received",
    quantity_open: float = 0,
    quantity_received: float = 1,
) -> None:
    now = datetime(2026, 6, 1, 12, 0, 0) - timedelta(days=days_ago)
    po = OrderProPurchaseOrder(
        orderpro_id=f"OP-PO-{product.id}-{days_ago}",
        purchase_order_number=f"PO-{product.id}-{days_ago}",
        status=status,
        order_date=now,
        created_at=now,
        updated_at=now,
    )
    db_session.add(po)
    db_session.flush()
    db_session.add(
        OrderProPurchaseOrderLine(
            orderpro_purchase_order_id=po.id,
            orderpro_line_id=f"L-{product.id}-{days_ago}",
            orderpro_line_key=f"L-{product.id}-{days_ago}",
            product_id=product.id,
            quantity_ordered=quantity_open + quantity_received,
            quantity_received=quantity_received,
            quantity_cancelled=0,
            quantity_open=quantity_open,
            unit_cost=unit_cost,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.flush()


def add_local_po_cost(db_session, product: Product, supplier: Supplier, unit_cost: float) -> None:
    now = datetime(2026, 6, 2, 12, 0, 0)
    po = PurchaseOrder(
        supplier_id=supplier.id,
        status="issued",
        created_at=now,
        updated_at=now,
    )
    db_session.add(po)
    db_session.flush()
    db_session.add(
        PurchaseOrderLine(
            purchase_order_id=po.id,
            product_id=product.id,
            quantity=1,
            unit_cost=unit_cost,
            line_total=unit_cost,
        )
    )
    db_session.flush()


def add_open_demand(db_session, product: Product, quantity: float) -> None:
    order = OrderProOrder(
        orderpro_id=f"SO-{product.id}",
        order_number=f"SO-{product.id}",
        status="confirmed",
        order_date=datetime(2026, 6, 1),
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderProOrderItem(
            order_id=order.id,
            product_id=product.id,
            orderpro_line_key=f"SO-{product.id}:1",
            quantity=0,
            quantity_ordered=quantity,
            quantity_shipped=0,
        )
    )
    db_session.flush()


def add_shipped_demand(db_session, product: Product, quantity: float = 5) -> None:
    recent_order_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    order = OrderProOrder(
        orderpro_id=f"SHIP-{product.id}",
        order_number=f"SHIP-{product.id}",
        status="shipped",
        order_date=recent_order_date,
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderProOrderItem(
            order_id=order.id,
            product_id=product.id,
            orderpro_line_key=f"SHIP-{product.id}:1",
            quantity=quantity,
            quantity_ordered=quantity,
            quantity_shipped=quantity,
        )
    )
    db_session.flush()


def add_pack_size_profile(db_session, product: Product, pack_size: float = 2, min_order_qty: float = 1) -> None:
    now = datetime(2026, 6, 1, 12, 0, 0)
    db_session.add(
        ProductForecastInputProfile(
            product_id=product.id,
            cost_price=None,
            cost_source="missing",
            cost_confidence="missing",
            lead_time_source="missing",
            lead_time_confidence="missing",
            min_order_qty=min_order_qty,
            moq_source="forecast_input_profile",
            pack_size=pack_size,
            pack_size_source="forecast_input_profile",
            safety_stock=0,
            safety_stock_source="product_record",
            blocking_issues=[],
            warning_issues=[],
            readiness_score=100,
            calculation_version="test",
            calculated_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.flush()


def test_effective_cost_prefers_orderpro_product_cost(db_session):
    supplier = make_supplier(db_session, lead_time_days=4)
    product = make_orderpro_product(db_session, supplier_id=supplier.id, cost_price=12.5)
    add_orderpro_po_cost(db_session, product, 8.0)

    inputs = effective_forecast_inputs(db_session, product)

    assert inputs["cost_price"] == 12.5
    assert inputs["cost_source"] == "orderpro_product_cost"
    assert inputs["cost_confidence"] == "high"


def test_forecast_product_cost_wins_over_po_derived_cost_metadata(db_session):
    supplier = make_supplier(db_session, lead_time_days=0)
    product = make_orderpro_product(db_session, supplier_id=supplier.id, min_order_qty=1, cost_price=9.0)
    add_orderpro_po_cost(db_session, product, 3.5)
    add_open_demand(db_session, product, 10)

    forecast = build_forecast(db_session, product)

    assert forecast["recommended_qty"] == 10
    assert forecast["estimated_unit_cost"] == 9.0
    assert forecast["estimated_cost_source"] == "orderpro_product_cost"
    assert forecast["estimated_purchase_value"] == 90
    assert forecast["forecast_input_context"]["cost_source"] == "orderpro_product_cost"


def test_live_product_cost_wins_over_stale_po_derived_profile(db_session):
    supplier = make_supplier(db_session, lead_time_days=0)
    product = make_orderpro_product(db_session, supplier_id=supplier.id, cost_price=9.0)
    now = datetime(2026, 6, 1, 12, 0, 0)
    db_session.add(
        ProductForecastInputProfile(
            product_id=product.id,
            cost_price=3.5,
            cost_source="orderpro_purchase_order_line",
            cost_confidence="medium",
            lead_time_source="missing",
            lead_time_confidence="missing",
            moq_source="business_default",
            pack_size_source="missing",
            safety_stock=0,
            safety_stock_source="product_record",
            blocking_issues=[],
            warning_issues=[],
            readiness_score=50,
            calculated_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.flush()

    inputs = profile_or_effective_inputs(db_session, product)

    assert inputs["cost_price"] == 9.0
    assert inputs["cost_source"] == "orderpro_product_cost"


def test_effective_cost_falls_back_to_latest_orderpro_purchase_order_line(db_session):
    supplier = make_supplier(db_session, lead_time_days=4)
    product = make_orderpro_product(db_session, supplier_id=supplier.id)
    add_orderpro_po_cost(db_session, product, 8.0, days_ago=5)
    add_orderpro_po_cost(db_session, product, 9.5, days_ago=0)

    inputs = effective_forecast_inputs(db_session, product)

    assert inputs["cost_price"] == 9.5
    assert inputs["cost_source"] == "orderpro_purchase_order_line"
    assert inputs["cost_confidence"] == "medium"


def test_effective_cost_falls_back_to_local_purchase_order_line(db_session):
    supplier = make_supplier(db_session, lead_time_days=4)
    product = make_orderpro_product(db_session, supplier_id=supplier.id)
    add_local_po_cost(db_session, product, supplier, 7.25)

    inputs = effective_forecast_inputs(db_session, product)

    assert inputs["cost_price"] == 7.25
    assert inputs["cost_source"] == "local_purchase_order_line"


def test_lead_time_moq_and_pack_size_sources_are_reported(db_session):
    supplier = make_supplier(db_session, lead_time_days=6)
    product = make_orderpro_product(db_session, supplier_id=supplier.id)
    product.pack_size = 12

    inputs = effective_forecast_inputs(db_session, product)

    assert inputs["lead_time_days"] == 6
    assert inputs["lead_time_source"] == "supplier_record"
    assert inputs["min_order_qty"] == 1
    assert inputs["moq_source"] == "business_default"
    assert inputs["pack_size"] == 12
    assert inputs["pack_size_source"] == "product_record"
    assert "fallback_moq" in inputs["warning_issues"]


def test_plan_and_apply_create_profiles_idempotently_without_product_mutation(db_session):
    supplier = make_supplier(db_session, lead_time_days=5)
    product = make_orderpro_product(db_session, supplier_id=supplier.id)
    add_orderpro_po_cost(db_session, product, 4.5)

    dry_run = plan_forecast_input_reconciliation(db_session)

    assert dry_run.summary["profiles_to_create"] == 1
    assert db_session.query(ProductForecastInputProfile).count() == 0
    assert product.cost_price is None

    applied = apply_forecast_input_reconciliation(db_session)
    first_profile = db_session.query(ProductForecastInputProfile).one()
    second = apply_forecast_input_reconciliation(db_session)

    assert applied.summary["profiles_created"] == 1
    assert first_profile.cost_price == 4.5
    assert first_profile.cost_source == "orderpro_purchase_order_line"
    assert first_profile.lead_time_days == 5
    assert db_session.query(ProductForecastInputProfile).count() == 1
    assert second.summary["profiles_created"] == 0
    assert product.cost_price is None


def test_forecast_uses_effective_cost_and_profile_source_metadata(db_session):
    supplier = make_supplier(db_session, lead_time_days=0)
    product = make_orderpro_product(db_session, supplier_id=supplier.id, min_order_qty=1)
    add_orderpro_po_cost(db_session, product, 3.5)
    add_open_demand(db_session, product, 10)

    forecast = build_forecast(db_session, product)

    assert forecast["recommended_qty"] == 10
    assert forecast["estimated_unit_cost"] == 3.5
    assert forecast["estimated_cost_source"] == "orderpro_purchase_order_line"
    assert forecast["estimated_purchase_value"] == 35
    assert forecast["forecast_input_context"]["cost_source"] == "orderpro_purchase_order_line"


def test_forecast_pack_size_from_reconciled_inputs_rounds_quantity(db_session):
    supplier = make_supplier(db_session, lead_time_days=0)
    product = make_orderpro_product(db_session, supplier_id=supplier.id, min_order_qty=1)
    product.pack_size = 6
    add_open_demand(db_session, product, 10)

    forecast = build_forecast(db_session, product)

    assert forecast["recommended_qty"] == 12
    assert forecast["pack_size"] == 6
    assert forecast["pack_size_source"] == "product_record"


def test_legacy_product_supplier_pack_size_does_not_round_orderpro_forecast(db_session):
    supplier = make_supplier(db_session, lead_time_days=0)
    product = make_orderpro_product(db_session, supplier_id=supplier.id, min_order_qty=1)
    db_session.add(
        ProductSupplier(
            product_id=product.id,
            supplier_id=supplier.id,
            supplier_sku="LEGACY",
            match_status="confirmed",
            pack_size=6,
            minimum_order_quantity=6,
        )
    )
    add_open_demand(db_session, product, 10)

    forecast = build_forecast(db_session, product)

    assert forecast["recommended_qty"] == 10
    assert forecast["pack_size"] is None
    assert forecast["pack_size_source"] == "missing"


def test_missing_supplier_context_remains_missing_with_moq_default(db_session):
    product = make_orderpro_product(db_session, supplier_id=None, min_order_qty=0)

    forecast = build_forecast(db_session, product)

    assert forecast["supplier_context"]["mapping_source"] == "missing"
    assert forecast["supplier_context"]["minimum_order_quantity"] == 0
    assert forecast["supplier_context"]["moq_source"] == "missing"
    assert forecast["supplier_context"]["needs_supplier_mapping"] is True
    assert "missing_supplier" in forecast["input_blocking_issues"]
    assert forecast["forecast_input_context"]["min_order_qty"] == 1
    assert forecast["forecast_input_context"]["moq_source"] == "business_default"


def test_readiness_summary_and_filters_include_reconciliation_sources(client, db_session):
    supplier = make_supplier(db_session, name="Ready Input Supplier", lead_time_days=5)
    ready = make_orderpro_product(
        db_session,
        name="Ready Input Product",
        orderpro_id="READY-INPUT",
        orderpro_sku="READY-INPUT",
        supplier_id=supplier.id,
    )
    missing = make_orderpro_product(
        db_session,
        name="Missing Input Product",
        orderpro_id="MISS-INPUT",
        orderpro_sku="MISS-INPUT",
        supplier_id=None,
    )
    add_orderpro_po_cost(db_session, ready, 6.0)
    db_session.commit()

    summary = client.get("/forecast-readiness/summary")
    detail = client.get(f"/products/{ready.id}/forecast-readiness")
    po_cost = client.get("/products/forecast-readiness", params={"filter": "po_derived_cost"})
    missing_supplier = client.get("/products/forecast-readiness", params={"filter": "missing_supplier"})

    assert summary.status_code == 200
    body = summary.json()
    assert body["product_count"] == 2
    assert body["products_using_po_derived_cost"] == 1
    assert body["products_using_fallback_moq"] == 2
    assert body["products_blocked_by_missing_supplier"] == 1
    assert detail.status_code == 200
    assert detail.json()["cost_source"] == "orderpro_purchase_order_line"
    assert detail.json()["lead_time_source"] == "supplier_record"
    assert po_cost.status_code == 200
    assert [row["product_id"] for row in po_cost.json()] == [ready.id]
    assert missing_supplier.status_code == 200
    assert [row["product_id"] for row in missing_supplier.json()] == [missing.id]


def test_forecast_input_audit_reports_supplier_and_cost_gaps(db_session):
    supplier = make_supplier(db_session, lead_time_days=None)
    make_orderpro_product(db_session, supplier_id=supplier.id)
    make_orderpro_product(db_session, orderpro_id="NO-SUP", orderpro_sku="NO-SUP", supplier_id=None)

    audit = forecast_input_audit(db_session)

    assert audit["total_orderpro_products"] == 2
    assert audit["products_missing_cost_price"] == 2
    assert audit["products_missing_supplier_id"] == 1
    assert audit["products_missing_usable_lead_time"] == 2
    assert audit["suppliers_missing_lead_time"] == 1


def test_forecast_reconciliation_ready_partially_blocked_and_monitor_categories(db_session):
    supplier = make_supplier(db_session, lead_time_days=5)
    ready = make_orderpro_product(
        db_session,
        orderpro_id="READY-CAT",
        orderpro_sku="READY-CAT",
        supplier_id=supplier.id,
        cost_price=10,
        min_order_qty=1,
    )
    ready.pack_size = 2
    add_pack_size_profile(db_session, ready)
    add_shipped_demand(db_session, ready)

    partial = make_orderpro_product(db_session, orderpro_id="PART-CAT", orderpro_sku="PART-CAT", supplier_id=supplier.id)
    add_shipped_demand(db_session, partial)

    blocked = make_orderpro_product(db_session, orderpro_id="BLOCK-CAT", orderpro_sku="BLOCK-CAT", supplier_id=None)
    add_shipped_demand(db_session, blocked)

    monitor = make_orderpro_product(db_session, orderpro_id="MON-CAT", orderpro_sku="MON-CAT", supplier_id=supplier.id, cost_price=5)

    assert evaluate_product_readiness(db_session, ready)["readiness_status"] == "ready"
    assert evaluate_product_readiness(db_session, partial)["readiness_status"] == "partially_ready"
    blocked_eval = evaluate_product_readiness(db_session, blocked)
    assert blocked_eval["readiness_status"] == "blocked"
    assert "missing_supplier" in blocked_eval["blocking_issues"]
    monitor_eval = evaluate_product_readiness(db_session, monitor)
    assert monitor_eval["readiness_status"] == "monitor_only"
    assert "demand_history" in monitor_eval["missing_inputs"]


def test_forecast_reconciliation_manual_supplier_source_is_reported(db_session):
    supplier = make_supplier(db_session, name="Triequestrian", lead_time_days=5)
    product = make_orderpro_product(db_session, supplier_id=supplier.id, cost_price=10)
    db_session.add(
        ProductSupplierAssignmentReview(
            product_id=product.id,
            suggested_supplier_id=supplier.id,
            suggestion_source="manual_supplier_cleanup",
            confidence_label="manual",
            confidence_score=1.0,
            status="confirmed",
            reviewed_supplier_id=supplier.id,
            reviewed_by="Maged",
            reviewed_at=datetime(2026, 6, 1),
        )
    )
    add_shipped_demand(db_session, product)

    detail = evaluate_product_readiness(db_session, product)

    assert detail["supplier_name"] == "Triequestrian"
    assert detail["supplier_source"] == "manual_supplier_cleanup"
    assert detail["inputs"]["supplier"]["source"] == "manual_supplier_cleanup"


def test_forecast_reconciliation_endpoints_filter_search_paginate_and_detail(client, db_session):
    supplier = make_supplier(db_session, name="Ready Supplier", lead_time_days=5)
    ready = make_orderpro_product(
        db_session,
        name="Blue Forecast Halter",
        orderpro_id="BLUE-FR",
        orderpro_sku="BLUE-FR",
        supplier_id=supplier.id,
        cost_price=10,
        min_order_qty=1,
    )
    ready.pack_size = 2
    add_pack_size_profile(db_session, ready)
    add_shipped_demand(db_session, ready)
    missing = make_orderpro_product(db_session, name="Missing Supplier Forecast", orderpro_id="MISS-FR", orderpro_sku="MISS-FR", supplier_id=None)
    db_session.commit()

    summary = client.get("/api/forecast-reconciliation/summary")
    searched = client.get("/api/forecast-reconciliation/products", params={"search": "Blue", "page": 1, "page_size": 1})
    filtered = client.get("/api/forecast-reconciliation/products", params={"status": "blocked", "missing_input": "supplier_id"})
    detail = client.get(f"/api/forecast-reconciliation/products/{ready.id}")

    assert summary.status_code == 200
    assert summary.json()["total_products"] == 2
    assert summary.json()["ready"] == 1
    assert summary.json()["blocked"] == 1
    assert searched.status_code == 200
    assert searched.json()["total"] == 1
    assert searched.json()["items"][0]["product_id"] == ready.id
    assert filtered.status_code == 200
    assert [row["product_id"] for row in filtered.json()["items"]] == [missing.id]
    assert detail.status_code == 200
    assert detail.json()["inputs"]["cost"]["source"] == "orderpro_product_cost"


def test_forecast_reconciliation_csv_export_respects_filters_and_sanitizes(client, db_session):
    supplier = make_supplier(db_session, name="=Formula Supplier", lead_time_days=5)
    product = make_orderpro_product(
        db_session,
        name="=Formula Product",
        orderpro_id="CSV-FR",
        orderpro_sku="@CSV-FR",
        supplier_id=supplier.id,
        cost_price=10,
        min_order_qty=1,
    )
    product.pack_size = 2
    add_pack_size_profile(db_session, product)
    add_shipped_demand(db_session, product)
    make_orderpro_product(db_session, name="Other Product", orderpro_id="OTHER-FR", orderpro_sku="OTHER-FR")
    db_session.commit()

    response = client.get("/api/forecast-reconciliation/export.csv", params={"status": "ready"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment;" in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")
    text = response.content.decode("utf-8-sig")
    assert "'=Formula Product" in text
    assert "'@CSV-FR" in text
    assert "Other Product" not in text


def test_forecast_reconciliation_auth_and_no_orderpro_calls(
    unauthenticated_client,
    client,
    admin_auth_headers,
    db_session,
    monkeypatch,
):
    product = make_orderpro_product(db_session)
    db_session.commit()

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("OrderPro client must not be used by forecast reconciliation.")

    monkeypatch.setattr("app.services.orderpro_client.OrderProClient.generic_get", fail_if_called)
    monkeypatch.setattr(settings, "auth_enabled", True)
    unauthenticated_client.headers.pop("authorization", None)
    unauthenticated_client.headers.pop("Authorization", None)
    assert unauthenticated_client.get("/api/forecast-reconciliation/summary").status_code == 401

    monkeypatch.setattr(settings, "auth_enabled", False)
    assert unauthenticated_client.get("/api/forecast-reconciliation/summary").status_code == 200

    monkeypatch.setattr(settings, "auth_enabled", True)
    client.headers.update(admin_auth_headers)
    response = client.get(f"/api/forecast-reconciliation/products/{product.id}")
    assert response.status_code == 200
