import csv
import io
from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.core.config import settings
from app.models.orderpro_order import OrderProOrder, OrderProOrderItem
from app.models.product import Product
from app.models.product_forecast_input_profile import ProductForecastInputProfile
from app.models.product_supplier import ProductSupplier
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.recommendation import Recommendation
from app.models.stale_demand_review_decision import StaleDemandReviewDecision
from app.models.supplier import Supplier
from app.models.usage_history import UsageHistory
from app.services.forecasting import calculate_usage_history_demand, legacy_usage_quantity


RECENT_DEMAND_DATE = date(2026, 7, 1)
STALE_DEMAND_DATE = date(2025, 1, 1)


def csv_rows(response):
    text = response.content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def seed_recommendation_product(
    db_session,
    *,
    match_status: str = "matched",
    product_overrides: dict | None = None,
    mapping_overrides: dict | None = None,
    supplier_overrides: dict | None = None,
):
    product_defaults = {
        "name": "Recommendation Product",
        "orderpro_id": "8182",
        "orderpro_sku": "REC-ORDERPRO-SKU",
        "source_system": "orderpro",
        "current_stock": 1,
        "safety_stock": 10,
        "min_order_qty": 1,
        "cost_price": 5.0,
    }
    product_defaults.update(product_overrides or {})
    product = Product(**product_defaults)
    supplier_defaults = {
        "name": "Recommendation Supplier",
        "normalized_name": "RECOMMENDATION SUPPLIER",
        "orderpro_id": f"supplier-{product.orderpro_id or product.name}",
        "orderpro_code": f"REC-SUP-{product.orderpro_id or product.name}",
        "lead_time_days": 4,
    }
    supplier_defaults.update(supplier_overrides or {})
    supplier = Supplier(**supplier_defaults)
    db_session.add_all([product, supplier])
    db_session.flush()

    mapping_defaults = {
        "product_id": product.id,
        "supplier_id": supplier.id,
        "supplier_sku": "REC-SKU",
        "supplier_product_name": "Recommendation Supplier Product",
        "purchase_price": 5.0,
        "currency": "USD",
        "minimum_order_quantity": 2,
        "pack_size": 2,
        "lead_time_days": 4,
        "match_status": match_status,
        "match_method": "test",
    }
    mapping_defaults.update(mapping_overrides or {})
    product.supplier_id = supplier.id
    product.supplier_sku = mapping_defaults["supplier_sku"]
    mapping = ProductSupplier(**mapping_defaults)
    db_session.add(mapping)
    db_session.add(
        UsageHistory(
            product_id=product.id,
            date=RECENT_DEMAND_DATE,
            qty_used=2,
            net_qty=2,
            source_system="test",
        )
    )
    db_session.commit()
    return product, supplier, mapping


def add_forecast_profile(
    db_session,
    product: Product,
    *,
    min_order_qty: float | None = 1,
    moq_source: str = "product_record",
    pack_size: float | None = 1,
    pack_size_source: str = "forecast_input_profile",
    cost_price: float | None = 5.0,
    lead_time_days: int | None = 4,
) -> ProductForecastInputProfile:
    now = datetime(2026, 7, 1)
    profile = ProductForecastInputProfile(
        product_id=product.id,
        cost_price=cost_price,
        cost_source="product_record" if cost_price is not None else "missing",
        cost_confidence="high" if cost_price is not None else "missing",
        cost_updated_at=None,
        lead_time_days=lead_time_days,
        lead_time_source="supplier_record" if lead_time_days is not None else "missing",
        lead_time_confidence="medium" if lead_time_days is not None else "missing",
        min_order_qty=min_order_qty,
        moq_source=moq_source,
        pack_size=pack_size,
        pack_size_source=pack_size_source,
        safety_stock=product.safety_stock,
        safety_stock_source="product_record",
        blocking_issues=[],
        warning_issues=[],
        readiness_score=100,
        calculation_version="test",
        calculated_at=now,
        created_at=now,
        updated_at=now,
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(product)
    return profile


def create_recommendation(client, product_id: int) -> dict:
    response = client.post(f"/recommendations/reorder/{product_id}")
    assert response.status_code == 201
    return response.json()


def accept_recommendation(client, recommendation_id: int, reviewed_by: str = "buyer") -> dict:
    response = client.post(
        f"/recommendations/{recommendation_id}/accept",
        json={"reviewed_by": reviewed_by},
    )
    assert response.status_code == 200
    return response.json()


def test_create_reorder_recommendation_for_product_with_orderpro_supplier(client, db_session):
    product, supplier, mapping = seed_recommendation_product(db_session)

    payload = create_recommendation(client, product.id)

    assert payload["product_id"] == product.id
    assert payload["supplier_id"] == supplier.id
    assert payload["product_supplier_id"] is None
    assert payload["recommendation_type"] == "reorder"
    assert payload["status"] == "pending_review"
    assert payload["recommended_quantity"] > 0
    assert payload["recommended_supplier_name"] == supplier.name
    assert payload["recommended_supplier_sku"] == product.supplier_sku
    assert payload["estimated_unit_cost"] == product.cost_price
    assert payload["currency"] is None


def test_recommendation_stores_input_forecast_and_supplier_snapshots(client, db_session):
    product, supplier, _mapping = seed_recommendation_product(db_session)

    payload = create_recommendation(client, product.id)

    assert payload["input_snapshot"]["product"]["id"] == product.id
    assert payload["input_snapshot"]["product"]["current_stock"] == product.current_stock
    assert payload["input_snapshot"]["orderpro_product_supplier"]["supplier_id"] == supplier.id
    assert payload["input_snapshot"]["orderpro_product_supplier"]["mapping_source"] == "orderpro_product_supplier"
    assert payload["forecast_snapshot"]["product_id"] == product.id
    assert payload["forecast_snapshot"]["current_stock"] == product.current_stock
    assert payload["forecast_snapshot"]["inventory_source"] == "product_record"
    assert payload["forecast_snapshot"]["recommended_qty"] > 0
    assert payload["supplier_context_snapshot"]["mapping_source"] == "orderpro_product_supplier"
    assert payload["supplier_context_snapshot"]["supplier_id"] == supplier.id
    assert payload["supplier_context_snapshot"]["supplier_name"] == supplier.name
    assert payload["supplier_context_snapshot"]["supplier_code"] == supplier.orderpro_code
    assert payload["supplier_context_snapshot"]["supplier_sku"] == product.supplier_sku
    assert payload["model_name"] is None
    assert payload["prompt_version"] is None
    assert payload["generated_by"] == "system"


def test_recommendation_uses_product_cost_price_and_supplier_sku(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"cost_price": 7.25},
        mapping_overrides={"purchase_price": 99.0, "supplier_sku": "LEGACY-PS-SKU"},
    )

    payload = create_recommendation(client, product.id)

    assert payload["recommended_supplier_sku"] == product.supplier_sku
    assert payload["estimated_unit_cost"] == 7.25


def test_recommendation_uses_open_demand_shortage_quantity(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    order = OrderProOrder(
        orderpro_id="rec-open-demand",
        order_number="SO-REC-OPEN",
        status="confirmed",
        order_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderProOrderItem(
            order=order,
            product=product,
            orderpro_line_key="rec-open-demand:1",
            orderpro_product_id=product.orderpro_id,
            sku=product.orderpro_sku,
            quantity=0,
            quantity_ordered=64,
            quantity_shipped=0,
        )
    )
    db_session.commit()

    payload = create_recommendation(client, product.id)

    assert payload["recommended_quantity"] == 64
    assert payload["forecast_snapshot"]["recommended_qty"] == 64
    assert payload["forecast_snapshot"]["recommended_action"] == "reorder"
    assert payload["forecast_snapshot"]["risk_level"] == "high"
    assert payload["forecast_snapshot"]["net_available_stock"] == -64


def test_recommendation_snapshot_includes_inbound_adjustment_fields(client, db_session):
    product, supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    order = OrderProOrder(
        orderpro_id="rec-inbound-open-demand",
        order_number="SO-REC-INBOUND",
        status="confirmed",
        order_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderProOrderItem(
            order=order,
            product=product,
            orderpro_line_key="rec-inbound-open-demand:1",
            orderpro_product_id=product.orderpro_id,
            sku=product.orderpro_sku,
            quantity=0,
            quantity_ordered=64,
            quantity_shipped=0,
        )
    )
    po = PurchaseOrder(supplier=supplier, status="approved", created_by="test")
    db_session.add(po)
    db_session.flush()
    db_session.add(
        PurchaseOrderLine(
            purchase_order=po,
            product=product,
            quantity=20,
            unit_cost=product.cost_price,
        )
    )
    db_session.commit()

    payload = create_recommendation(client, product.id)

    assert payload["recommended_quantity"] == 44
    assert payload["forecast_snapshot"]["incoming_qty"] == 20
    assert payload["forecast_snapshot"]["recommended_qty_before_inbound"] == 64
    assert payload["forecast_snapshot"]["recommended_qty_after_inbound"] == 44
    assert payload["input_snapshot"]["inbound_stock"]["incoming_qty"] == 20
    assert payload["input_snapshot"]["inbound_stock"]["inbound_adjustment_qty"] == 20


def test_product_supplier_is_not_selected_over_orderpro_product_supplier(client, db_session):
    product, supplier, mapping = seed_recommendation_product(db_session)
    other_supplier = Supplier(
        name="Legacy Mapping Supplier",
        normalized_name="LEGACY MAPPING SUPPLIER",
    )
    db_session.add(other_supplier)
    db_session.flush()
    mapping.supplier_id = other_supplier.id
    mapping.supplier_sku = "LEGACY-MAPPING-SKU"
    mapping.purchase_price = 123.0
    db_session.commit()

    payload = create_recommendation(client, product.id)

    assert payload["supplier_id"] == supplier.id
    assert payload["product_supplier_id"] is None
    assert payload["recommended_supplier_sku"] == product.supplier_sku
    assert payload["estimated_unit_cost"] == product.cost_price


def test_recommendation_does_not_create_purchase_order_automatically(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)

    payload = create_recommendation(client, product.id)

    assert payload["converted_purchase_order_id"] is None
    assert db_session.query(PurchaseOrder).count() == 0


def test_recommendation_without_supplier_mapping_is_blocked_safely(client, db_session):
    product = Product(name="Unmapped Recommendation Product", current_stock=1)
    db_session.add(product)
    db_session.commit()

    response = client.post(f"/recommendations/reorder/{product.id}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Product is missing a canonical supplier assignment."
    assert db_session.query(Recommendation).count() == 0


def test_legacy_supplier_text_does_not_create_actionable_recommendation_without_supplier_id(client, db_session):
    product = Product(
        name="Legacy Supplier Recommendation Product",
        supplier="Legacy Supplier Text",
        current_stock=1,
        safety_stock=10,
        lead_time_days=4,
        min_order_qty=1,
    )
    db_session.add(product)
    db_session.flush()
    db_session.add(
        UsageHistory(
            product_id=product.id,
            date=RECENT_DEMAND_DATE,
            qty_used=2,
            net_qty=2,
            source_system="test",
        )
    )
    db_session.commit()

    response = client.post(f"/recommendations/reorder/{product.id}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Product is missing a canonical supplier assignment."
    assert db_session.query(Recommendation).count() == 0


def test_reorder_recommendation_requires_demand_signal(client, db_session):
    supplier = Supplier(
        name="No Demand Supplier",
        normalized_name="NO DEMAND SUPPLIER",
        orderpro_id="supplier-no-demand",
        orderpro_code="NO-DEMAND",
        lead_time_days=4,
    )
    product = Product(
        name="No Demand Product",
        orderpro_id="no-demand-product",
        orderpro_sku="NO-DEMAND",
        source_system="orderpro",
        supplier_record=supplier,
        current_stock=0,
        safety_stock=10,
        min_order_qty=1,
        cost_price=5.0,
    )
    db_session.add_all([supplier, product])
    db_session.commit()

    response = client.post(f"/recommendations/reorder/{product.id}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Product is missing demand history or open demand."
    assert db_session.query(Recommendation).count() == 0


def test_explain_recommendation_for_actionable_low_stock_product(client, db_session):
    product, supplier, _mapping = seed_recommendation_product(db_session)

    response = client.get(f"/recommendations/explain?product_id={product.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["product_id"] == product.id
    assert payload["product_name"] == product.name
    assert payload["supplier_id"] == supplier.id
    assert payload["supplier_name"] == supplier.name
    assert payload["status"] == "actionable"
    assert payload["recommended_quantity"] > 0
    assert payload["current_stock"] == product.current_stock
    assert payload["demand_quantity_mode"] == "net_qty"
    assert payload["demand_policy_status"] == "recent_or_current"
    assert payload["stale_demand_only"] is False
    assert payload["stale_demand_policy"] == "recent_or_not_legacy"
    assert payload["demand_rows"] == 1
    assert payload["monthly_average_demand"] > 0
    assert payload["lead_time_days"] == supplier.lead_time_days
    assert payload["blockers"] == []
    assert any("supplier assigned" in reason for reason in payload["reasons"])
    assert any("demand history" in reason for reason in payload["reasons"])


def test_purchase_readiness_order_ready_with_valid_moq_and_pack_size(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)
    add_forecast_profile(db_session, product, min_order_qty=1, pack_size=1)

    response = client.get(f"/recommendations/explain?product_id={product.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "actionable"
    assert payload["purchase_readiness_status"] == "order_ready"
    assert payload["not_ready_for_po"] is False
    assert payload["pack_size"] == 1
    assert payload["quantity_satisfies_moq"] is True
    assert payload["quantity_satisfies_pack_size"] is True
    assert payload["suggested_cleanup_action"] == "none"


def test_missing_pack_size_is_advisory_when_pack_size_not_required(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)

    response = client.get(f"/recommendations/explain?product_id={product.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "actionable"
    assert payload["purchase_readiness_status"] == "order_ready"
    assert payload["not_ready_for_po"] is False
    assert payload["pack_size"] is None
    assert payload["pack_size_required"] is False
    assert "Missing pack size" not in payload["purchase_readiness_issues"]
    assert any("Missing pack size" in warning for warning in payload["warnings"])
    assert payload["suggested_cleanup_action"] == "none"
    assert payload["quantity_review_note"] == "Ready for PO using current MOQ and pack-size inputs."


def test_missing_pack_size_blocks_when_pack_size_required(monkeypatch, client, db_session):
    monkeypatch.setattr(settings, "recommendation_require_pack_size", True)
    product, _supplier, _mapping = seed_recommendation_product(db_session)

    explain_response = client.get(f"/recommendations/explain?product_id={product.id}")
    create_response = client.post(f"/recommendations/reorder/{product.id}")

    assert explain_response.status_code == 200
    payload = explain_response.json()
    assert payload["purchase_readiness_status"] == "blocked"
    assert payload["pack_size_required"] is True
    assert "Missing pack size" in payload["purchase_readiness_issues"]
    assert payload["suggested_cleanup_action"] == "update_after_pack_size_fix"
    assert "pack size is required" in payload["quantity_review_note"]
    assert create_response.status_code == 400
    assert create_response.json()["detail"] == "Product is missing required pack size."


def test_create_recommendation_allows_optional_missing_pack_size(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)

    response = client.post(f"/recommendations/reorder/{product.id}")

    assert response.status_code == 201
    payload = response.json()
    assert payload["forecast_snapshot"]["purchase_readiness_status"] == "order_ready"
    assert payload["forecast_snapshot"]["pack_size_required"] is False
    assert payload["forecast_snapshot"]["not_ready_for_po"] is False


def test_missing_cost_warns_when_cost_not_required(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session, product_overrides={"cost_price": None})

    explain_response = client.get(f"/recommendations/explain?product_id={product.id}")
    create_response = client.post(f"/recommendations/reorder/{product.id}")

    assert explain_response.status_code == 200
    payload = explain_response.json()
    assert payload["cost_required"] is False
    assert payload["cost_status"] == "missing"
    assert payload["purchase_readiness_status"] == "needs_review"
    assert "Missing cost" in payload["purchase_readiness_issues"]
    assert payload["suggested_cleanup_action"] == "review_missing_cost"
    assert create_response.status_code == 201
    assert create_response.json()["estimated_unit_cost"] is None


def test_missing_cost_blocks_when_cost_required(monkeypatch, client, db_session):
    monkeypatch.setattr(settings, "recommendation_require_cost", True)
    product, _supplier, _mapping = seed_recommendation_product(db_session, product_overrides={"cost_price": None})

    explain_response = client.get(f"/recommendations/explain?product_id={product.id}")
    create_response = client.post(f"/recommendations/reorder/{product.id}")

    assert explain_response.status_code == 200
    payload = explain_response.json()
    assert payload["cost_required"] is True
    assert payload["cost_status"] == "missing"
    assert payload["purchase_readiness_status"] == "blocked"
    assert "Missing cost" in payload["purchase_readiness_issues"]
    assert create_response.status_code == 400
    assert create_response.json()["detail"] == "Product is missing required cost."


def test_quantity_below_moq_is_raised_and_flagged_for_review(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 0},
    )
    add_forecast_profile(db_session, product, min_order_qty=10, moq_source="forecast_input_profile", pack_size=1)

    response = client.get(f"/recommendations/explain?product_id={product.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_quantity"] == 10
    assert payload["minimum_order_quantity"] == 10
    assert payload["quantity_satisfies_moq"] is True
    assert payload["quantity_was_raised_to_moq"] is True
    assert payload["purchase_readiness_status"] == "needs_review"
    assert "Quantity was raised to MOQ" in payload["purchase_readiness_issues"]


def test_quantity_rounded_to_pack_size_is_flagged_for_review(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)
    add_forecast_profile(db_session, product, min_order_qty=1, pack_size=5)

    response = client.get(f"/recommendations/explain?product_id={product.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_quantity"] == 20
    assert payload["quantity_satisfies_pack_size"] is True
    assert payload["quantity_was_rounded_to_pack_size"] is True
    assert payload["purchase_readiness_status"] == "needs_review"
    assert "Quantity was rounded to pack size" in payload["purchase_readiness_issues"]


def test_legacy_net_qty_reduces_returns_in_forecast_demand(db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)
    db_session.add(
        UsageHistory(
            product_id=product.id,
            date=date(2026, 7, 2),
            qty_used=0,
            qty_returned=1,
            net_qty=-1,
            source_system="test",
        )
    )
    db_session.commit()

    demand = calculate_usage_history_demand(db_session, product.id, quantity_mode="net_qty", today=RECENT_DEMAND_DATE)
    qty_used_demand = calculate_usage_history_demand(db_session, product.id, quantity_mode="qty_used", today=RECENT_DEMAND_DATE)

    assert demand.units_sold_in_window == 1
    assert demand.legacy_raw_units_in_window == 1
    assert demand.legacy_negative_or_return_rows == 1
    assert qty_used_demand.units_sold_in_window == 2


def test_missing_net_qty_falls_back_to_qty_used():
    row = SimpleNamespace(qty_used=7, net_qty=None)

    assert legacy_usage_quantity(row, "net_qty") == 7


def test_negative_net_legacy_demand_does_not_create_actionable_reorder(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history.clear()
    db_session.flush()
    db_session.add(
        UsageHistory(
            product_id=product.id,
            date=RECENT_DEMAND_DATE,
            qty_used=0,
            qty_returned=5,
            net_qty=-5,
            source_system="test",
        )
    )
    db_session.commit()

    explain_response = client.get(f"/recommendations/explain?product_id={product.id}")
    create_response = client.post(f"/recommendations/reorder/{product.id}")

    assert explain_response.status_code == 200
    payload = explain_response.json()
    assert payload["status"] == "monitor"
    assert payload["recommended_quantity"] == 0
    assert "Returns or negative rows affected legacy demand calculation" in payload["warnings"]
    assert create_response.status_code == 400
    assert create_response.json()["detail"] == "Product is not currently recommended for reorder."


def test_stale_only_legacy_demand_requires_review_but_explains_advisory_quantity(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.commit()

    explain_response = client.get(f"/recommendations/explain?product_id={product.id}")
    create_response = client.post(f"/recommendations/reorder/{product.id}")

    assert explain_response.status_code == 200
    payload = explain_response.json()
    assert payload["status"] == "needs_review"
    assert payload["readiness_status"] == "partially_ready"
    assert payload["stale_demand_only"] is True
    assert payload["stale_demand_policy"] == "manual_review_required"
    assert payload["recommended_quantity"] > 0
    assert payload["purchase_readiness_status"] == "blocked"
    assert "Stale-only demand requires manual review" in payload["purchase_readiness_issues"]
    assert any(warning.startswith("Stale demand only") for warning in payload["warnings"])
    assert create_response.status_code == 400
    assert create_response.json()["detail"] == "Product has stale-only legacy demand and requires manual review."


def test_stale_demand_review_lists_stale_reorder_candidate_read_only(client, db_session):
    product, supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.commit()
    product_count = db_session.query(Product).count()
    recommendation_count = db_session.query(Recommendation).count()

    response = client.get("/recommendations/stale-demand-review")

    assert response.status_code == 200
    payload = response.json()
    assert db_session.query(Product).count() == product_count
    assert db_session.query(Recommendation).count() == recommendation_count
    assert payload["summary"]["total_candidates"] == 1
    item = payload["items"][0]
    assert item["product_id"] == product.id
    assert item["supplier_id"] == supplier.id
    assert item["last_demand_date"] == STALE_DEMAND_DATE.isoformat()
    assert item["days_since_last_demand"] > 180
    assert item["demand_rows"] == 1
    assert item["monthly_average_demand"] > 0
    assert item["current_stock"] == 0
    assert item["lead_time_days"] == supplier.lead_time_days
    assert item["advisory_recommended_quantity"] > 0
    assert "Stale-only demand requires manual review" in item["purchase_readiness_issues"]
    assert item["suggested_action"] in {"manual_review", "approve_one_time_reorder"}


def test_stale_demand_review_excludes_recent_demand_product(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)

    response = client.get("/recommendations/stale-demand-review")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_candidates"] == 0
    assert all(item["product_id"] != product.id for item in payload["items"])


def test_stale_demand_review_excludes_missing_supplier_blocker(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    product.supplier_id = None
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.add(
        Recommendation(
            product_id=product.id,
            recommended_qty=2,
            risk_level="medium",
            recommendation_type="reorder",
            status="pending_review",
            reason="Existing stale recommendation with missing supplier.",
            generated_by="test",
        )
    )
    db_session.commit()

    review_response = client.get("/recommendations/stale-demand-review")
    cleanup_response = client.get("/recommendations/cleanup-candidates")

    assert review_response.status_code == 200
    assert review_response.json()["summary"]["total_candidates"] == 0
    assert cleanup_response.status_code == 200
    cleanup_item = cleanup_response.json()["candidates"][0]
    assert cleanup_item["product_id"] == product.id
    assert "missing supplier" in cleanup_item["issues"]
    assert cleanup_item["suggested_action"] == "update_after_supplier_fix"


def test_stale_demand_review_excludes_zero_advisory_quantity(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 100, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.commit()

    response = client.get("/recommendations/stale-demand-review")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_candidates"] == 0
    assert all(item["product_id"] != product.id for item in payload["items"])


def test_stale_demand_decision_manager_approved_allows_manual_recommendation_without_po(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.commit()
    before_po_count = db_session.query(PurchaseOrder).count()
    before_forecast = client.get(f"/recommendations/explain?product_id={product.id}").json()

    blocked_response = client.post(f"/recommendations/reorder/{product.id}")
    decision_response = client.post(
        f"/recommendations/stale-demand-review/{product.id}/decision",
        json={
            "decision": "manager_approved_one_time",
            "reviewed_by": "Maged",
            "notes": "Approved one-time stale-demand reorder.",
        },
    )
    after_forecast = client.get(f"/recommendations/explain?product_id={product.id}").json()
    create_response = client.post(f"/recommendations/reorder/{product.id}")

    assert blocked_response.status_code == 400
    assert decision_response.status_code == 200
    assert decision_response.json()["decision"] == "manager_approved_one_time"
    assert decision_response.json()["reviewed_by"] == "Maged"
    assert after_forecast["review_decision"] == "manager_approved_one_time"
    assert after_forecast["reviewed_by"] == "Maged"
    assert after_forecast["recommended_quantity"] == before_forecast["recommended_quantity"]
    assert after_forecast["reorder_point"] == before_forecast["reorder_point"]
    assert create_response.status_code == 201
    assert create_response.json()["forecast_snapshot"]["review_decision"] == "manager_approved_one_time"
    assert db_session.query(PurchaseOrder).count() == before_po_count


def test_stale_demand_decision_watchlist_is_saved(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)

    response = client.post(
        f"/recommendations/stale-demand-review/{product.id}/decision",
        json={"decision": "watchlist", "reviewed_by": "Maged", "notes": "Do not reorder yet."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["product_id"] == product.id
    assert payload["decision"] == "watchlist"
    assert payload["notes"] == "Do not reorder yet."
    stored = db_session.query(StaleDemandReviewDecision).filter_by(product_id=product.id).one()
    assert stored.decision == "watchlist"


def test_stale_demand_decision_rejects_invalid_decision_and_requires_reviewer(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)

    invalid_response = client.post(
        f"/recommendations/stale-demand-review/{product.id}/decision",
        json={"decision": "approve_forever", "reviewed_by": "Maged"},
    )
    missing_reviewer_response = client.post(
        f"/recommendations/stale-demand-review/{product.id}/decision",
        json={"decision": "watchlist", "reviewed_by": ""},
    )

    assert invalid_response.status_code == 400
    assert invalid_response.json()["detail"] == "Invalid stale-demand review decision."
    assert missing_reviewer_response.status_code == 422


def test_stale_demand_decision_endpoint_does_not_change_forecast_formula(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.commit()
    before = client.get(f"/recommendations/explain?product_id={product.id}").json()

    response = client.post(
        f"/recommendations/stale-demand-review/{product.id}/decision",
        json={"decision": "wait_for_recent_demand", "reviewed_by": "Maged"},
    )
    after = client.get(f"/recommendations/explain?product_id={product.id}").json()

    assert response.status_code == 200
    assert after["recommended_quantity"] == before["recommended_quantity"]
    assert after["recommended_action"] == before["recommended_action"]
    assert after["reorder_point"] == before["reorder_point"]


def test_stale_demand_review_endpoint_includes_decision_fields_and_filters_rejected(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.commit()
    client.post(
        f"/recommendations/stale-demand-review/{product.id}/decision",
        json={"decision": "rejected_stale", "reviewed_by": "Maged", "notes": "Discontinued."},
    )

    default_response = client.get("/recommendations/stale-demand-review")
    all_response = client.get("/recommendations/stale-demand-review?decision=all")
    rejected_response = client.get("/recommendations/stale-demand-review?decision=rejected_stale")

    assert default_response.status_code == 200
    assert all(item["product_id"] != product.id for item in default_response.json()["items"])
    assert all_response.status_code == 200
    all_item = next(item for item in all_response.json()["items"] if item["product_id"] == product.id)
    assert all_item["review_decision"] == "rejected_stale"
    assert all_item["reviewed_by"] == "Maged"
    assert all_item["review_notes"] == "Discontinued."
    assert all_item["decision_status"] == "rejected_stale"
    assert rejected_response.status_code == 200
    assert rejected_response.json()["items"][0]["product_id"] == product.id


def test_non_stale_product_cannot_be_manager_approved_as_stale_reorder(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)

    response = client.post(
        f"/recommendations/stale-demand-review/{product.id}/decision",
        json={"decision": "manager_approved_one_time", "reviewed_by": "Maged"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Product is not currently eligible for this stale-demand decision."


def test_manager_approved_stale_queue_lists_ready_candidate(client, db_session):
    product, supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    add_forecast_profile(db_session, product, pack_size=1, cost_price=5.0, lead_time_days=4)
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.commit()
    client.post(
        f"/recommendations/stale-demand-review/{product.id}/decision",
        json={
            "decision": "manager_approved_one_time",
            "reviewed_by": "Maged",
            "notes": "One-time review approved.",
        },
    )

    response = client.get("/recommendations/manager-approved-stale-queue")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_candidates"] == 1
    item = payload["items"][0]
    assert item["product_id"] == product.id
    assert item["supplier_id"] == supplier.id
    assert item["reviewed_by"] == "Maged"
    assert item["review_notes"] == "One-time review approved."
    assert item["safety_status"] == "ready_for_manual_recommendation"
    assert item["safety_blockers"] == []
    assert item["suggested_next_action"] == "create_review_recommendation"


def test_manager_approved_stale_queue_excludes_other_decisions(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.commit()
    for decision in ("watchlist", "rejected_stale", "wait_for_recent_demand"):
        client.post(
            f"/recommendations/stale-demand-review/{product.id}/decision",
            json={"decision": decision, "reviewed_by": "Maged"},
        )
        response = client.get("/recommendations/manager-approved-stale-queue")
        assert response.status_code == 200
        assert response.json()["summary"]["total_candidates"] == 0


def test_manager_approved_stale_queue_marks_missing_supplier_as_blocked(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history[0].date = STALE_DEMAND_DATE
    product.supplier_id = None
    db_session.add(
        StaleDemandReviewDecision(
            product_id=product.id,
            decision="manager_approved_one_time",
            reviewed_by="Maged",
            reviewed_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    response = client.get("/recommendations/manager-approved-stale-queue")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["product_id"] == product.id
    assert item["safety_status"] == "blocked"
    assert "Missing supplier" in item["safety_blockers"]


def test_manager_approved_stale_queue_marks_non_positive_quantity_as_blocked(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 100, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.add(
        StaleDemandReviewDecision(
            product_id=product.id,
            decision="manager_approved_one_time",
            reviewed_by="Maged",
            reviewed_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    response = client.get("/recommendations/manager-approved-stale-queue")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["safety_status"] == "blocked"
    assert "Non-positive recommendation quantity" in item["safety_blockers"]
    assert "Forecast action is not reorder" in item["safety_blockers"]


def test_manager_approved_stale_queue_is_read_only(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.add(
        StaleDemandReviewDecision(
            product_id=product.id,
            decision="manager_approved_one_time",
            reviewed_by="Maged",
            reviewed_at=datetime.utcnow(),
        )
    )
    db_session.commit()
    before_recommendations = db_session.query(Recommendation).count()
    before_purchase_orders = db_session.query(PurchaseOrder).count()

    response = client.get("/recommendations/manager-approved-stale-queue")

    assert response.status_code == 200
    assert db_session.query(Recommendation).count() == before_recommendations
    assert db_session.query(PurchaseOrder).count() == before_purchase_orders


def test_manager_approved_stale_create_review_requires_decision(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.commit()

    response = client.post(
        f"/recommendations/manager-approved-stale-queue/{product.id}/create-review-recommendation"
    )

    assert response.status_code == 400
    assert "Latest stale-demand decision is not manager-approved one-time" in response.json()["detail"]


def test_manager_approved_stale_create_review_refuses_non_eligible_product(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 100, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.add(
        StaleDemandReviewDecision(
            product_id=product.id,
            decision="manager_approved_one_time",
            reviewed_by="Maged",
            reviewed_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    response = client.post(
        f"/recommendations/manager-approved-stale-queue/{product.id}/create-review-recommendation"
    )

    assert response.status_code == 400
    assert "Non-positive recommendation quantity" in response.json()["detail"]


def test_manager_approved_stale_create_review_creates_pending_review_without_po_and_no_duplicates(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    add_forecast_profile(db_session, product, pack_size=1, cost_price=5.0, lead_time_days=4)
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.commit()
    client.post(
        f"/recommendations/stale-demand-review/{product.id}/decision",
        json={"decision": "manager_approved_one_time", "reviewed_by": "Maged"},
    )
    before_po_count = db_session.query(PurchaseOrder).count()

    first_response = client.post(
        f"/recommendations/manager-approved-stale-queue/{product.id}/create-review-recommendation",
        json={"created_by": "Maged"},
    )
    second_response = client.post(
        f"/recommendations/manager-approved-stale-queue/{product.id}/create-review-recommendation",
        json={"created_by": "Maged"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_payload = first_response.json()
    second_payload = second_response.json()
    assert first_payload["id"] == second_payload["id"]
    assert first_payload["status"] == "pending_review"
    assert first_payload["forecast_snapshot"]["review_decision"] == "manager_approved_one_time"
    assert first_payload["converted_purchase_order_id"] is None
    assert db_session.query(PurchaseOrder).count() == before_po_count
    assert (
        db_session.query(Recommendation)
        .filter(Recommendation.product_id == product.id)
        .filter(Recommendation.status == "pending_review")
        .count()
        == 1
    )


def test_recommendation_review_summary_counts_decisions_queue_and_cleanup(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    add_forecast_profile(db_session, product, pack_size=1, cost_price=5.0, lead_time_days=4)
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.add(
        Recommendation(
            product_id=product.id,
            supplier_id=product.supplier_id,
            recommended_qty=3,
            risk_level="medium",
            recommendation_type="reorder",
            status="pending_review",
            reason="Existing stale recommendation.",
            generated_by="test",
        )
    )
    db_session.commit()
    client.post(
        f"/recommendations/stale-demand-review/{product.id}/decision",
        json={"decision": "manager_approved_one_time", "reviewed_by": "Maged"},
    )

    response = client.get("/recommendations/review-summary")

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["total_existing_recommendations"] == 1
    assert summary["pending_review_recommendations"] == 1
    assert summary["stale_demand_decisions_by_type"]["manager_approved_one_time"] == 1
    assert summary["manager_approved_stale_queue_count"] == 1
    assert summary["manager_approved_stale_queue_by_safety_status"]["ready_for_manual_recommendation"] == 1
    assert summary["cleanup_candidates_count"] == 1
    assert summary["cleanup_candidates_by_issue"]["stale_demand_review_required"] == 1


def test_stale_demand_review_csv_export_returns_expected_headers(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.commit()

    response = client.get("/recommendations/stale-demand-review/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "stale_demand_review_" in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")
    rows = csv_rows(response)
    assert rows[0]["Product ID"] == str(product.id)
    assert rows[0]["Product Name"] == product.name
    assert "Review Decision" in rows[0]
    assert "Review Notes" in rows[0]


def test_manager_approved_queue_csv_export_returns_expected_headers(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    add_forecast_profile(db_session, product, pack_size=1, cost_price=5.0, lead_time_days=4)
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.commit()
    client.post(
        f"/recommendations/stale-demand-review/{product.id}/decision",
        json={"decision": "manager_approved_one_time", "reviewed_by": "Maged", "notes": "Approved."},
    )

    response = client.get("/recommendations/manager-approved-stale-queue/export.csv")

    assert response.status_code == 200
    rows = csv_rows(response)
    assert rows[0]["Product ID"] == str(product.id)
    assert rows[0]["Reviewed By"] == "Maged"
    assert rows[0]["Safety Status"] == "ready_for_manual_recommendation"
    assert "Safety Blockers" in rows[0]
    assert "Warnings" in rows[0]


def test_cleanup_candidates_csv_export_returns_expected_headers(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.add(
        Recommendation(
            product_id=product.id,
            supplier_id=product.supplier_id,
            recommended_qty=3,
            risk_level="medium",
            recommendation_type="reorder",
            status="pending_review",
            reason="Existing stale recommendation.",
            generated_by="test",
        )
    )
    db_session.commit()

    response = client.get("/recommendations/cleanup-candidates/export.csv")

    assert response.status_code == 200
    rows = csv_rows(response)
    assert rows[0]["Product ID"] == str(product.id)
    assert rows[0]["Recommendation ID"]
    assert "Issues" in rows[0]
    assert "Blockers" in rows[0]
    assert "Warnings" in rows[0]


def test_review_summary_csv_export_returns_metric_rows(client, db_session):
    seed_recommendation_product(db_session)

    response = client.get("/recommendations/review-summary/export.csv")

    assert response.status_code == 200
    rows = csv_rows(response)
    assert rows[0] == {"Metric": "total_existing_recommendations", "Value": "0"}
    metrics = {row["Metric"] for row in rows}
    assert "stale_demand_candidates" in metrics
    assert "cleanup_candidates_count" in metrics


def test_recommendation_review_exports_are_read_only(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={"current_stock": 0, "safety_stock": 0, "min_order_qty": 1},
    )
    product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.commit()
    before_recommendations = db_session.query(Recommendation).count()
    before_purchase_orders = db_session.query(PurchaseOrder).count()

    for path in (
        "/recommendations/stale-demand-review/export.csv",
        "/recommendations/manager-approved-stale-queue/export.csv",
        "/recommendations/cleanup-candidates/export.csv",
        "/recommendations/review-summary/export.csv",
    ):
        response = client.get(path)
        assert response.status_code == 200

    assert db_session.query(Recommendation).count() == before_recommendations
    assert db_session.query(PurchaseOrder).count() == before_purchase_orders


def test_recommendation_review_exports_require_authentication_when_enabled(unauthenticated_client, db_session):
    response = unauthenticated_client.get("/recommendations/review-summary/export.csv")

    assert response.status_code == 401


def test_demand_policy_impact_endpoint_reports_stale_and_recent_policy_changes(client, db_session):
    seed_recommendation_product(db_session)
    stale_product, _supplier, _mapping = seed_recommendation_product(
        db_session,
        product_overrides={
            "name": "Stale Demand Product",
            "orderpro_id": "stale-demand-product",
            "orderpro_sku": "STALE-DEMAND",
            "current_stock": 0,
            "safety_stock": 0,
        },
        supplier_overrides={
            "name": "Stale Demand Supplier",
            "normalized_name": "STALE DEMAND SUPPLIER",
            "orderpro_id": "supplier-stale-demand",
            "orderpro_code": "STALE-SUP",
        },
    )
    stale_product.usage_history[0].date = STALE_DEMAND_DATE
    db_session.commit()

    response = client.get("/recommendations/demand-policy-impact?lookback_days=180&quantity_mode=net_qty&stale_days=180")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_products_evaluated"] == 2
    assert payload["summary"]["actionable_current_policy"] == 1
    assert payload["summary"]["stale_only_needs_review_count"] == 1
    assert payload["summary"]["products_where_recommendation_status_changes"] >= 1
    assert any(example["product_id"] == stale_product.id for example in payload["examples"])


def test_explain_recommendation_for_blocked_product_lists_blockers(client, db_session):
    product = Product(name="Blocked Recommendation Product", current_stock=None)
    db_session.add(product)
    db_session.commit()

    response = client.get(f"/recommendations/explain?product_id={product.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert "Missing supplier" in payload["blockers"]
    assert "No demand history" in payload["blockers"]
    assert "Missing lead time" in payload["blockers"]
    assert payload["recommended_quantity"] == 0
    assert payload["purchase_readiness_status"] == "blocked"
    assert "Missing supplier" in payload["purchase_readiness_issues"]


def test_recommendation_audit_flags_suspicious_stored_recommendation(client, db_session):
    product = Product(name="Suspicious Stored Recommendation Product", current_stock=10)
    db_session.add(product)
    db_session.flush()
    db_session.add(
        Recommendation(
            product_id=product.id,
            recommended_qty=1,
            risk_level="medium",
            recommendation_type="reorder",
            status="pending_review",
            reason="Legacy recommendation created before supplier cleanup.",
            generated_by="test",
        )
    )
    db_session.commit()

    response = client.get("/recommendations/audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["recommendations_evaluated"] == 1
    assert payload["summary"]["suspicious_recommendations"] == 1
    item = payload["items"][0]
    assert item["product_id"] == product.id
    assert item["explanation_status"] == "blocked"
    assert "Actionable recommendation is missing supplier" in item["suspicious_issues"]
    assert "Actionable recommendation has no demand history" in item["suspicious_issues"]
    assert item["purchase_readiness_status"] == "blocked"


def test_cleanup_candidates_endpoint_reports_stale_actionable_existing_row_read_only(client, db_session):
    product, supplier, _mapping = seed_recommendation_product(db_session)
    add_forecast_profile(db_session, product, min_order_qty=1, pack_size=1)
    product.usage_history[0].date = STALE_DEMAND_DATE
    recommendation = Recommendation(
        product_id=product.id,
        supplier_id=supplier.id,
        recommended_qty=2,
        risk_level="medium",
        recommendation_type="reorder",
        status="pending_review",
        reason="Existing stale recommendation row.",
        generated_by="test",
    )
    db_session.add(recommendation)
    db_session.commit()
    recommendation_id = recommendation.id

    before_count = db_session.query(Recommendation).count()
    response = client.get("/recommendations/cleanup-candidates")
    db_session.expire_all()
    stored = db_session.get(Recommendation, recommendation_id)

    assert response.status_code == 200
    payload = response.json()
    assert db_session.query(Recommendation).count() == before_count
    assert stored.status == "pending_review"
    assert payload["summary"]["total_candidates"] == 1
    assert payload["summary"]["issue_counts"]["stale_demand_review_required"] == 1
    candidate = payload["candidates"][0]
    assert candidate["product_id"] == product.id
    assert candidate["purchase_readiness_status"] == "blocked"
    assert "stale_demand_review_required" in candidate["issues"]
    assert candidate["suggested_action"] == "review_stale_demand"


def test_cleanup_candidates_exclude_optional_missing_pack_size_only(client, db_session):
    product, supplier, _mapping = seed_recommendation_product(db_session)
    recommendation = Recommendation(
        product_id=product.id,
        supplier_id=supplier.id,
        recommended_qty=2,
        risk_level="medium",
        recommendation_type="reorder",
        status="pending_review",
        reason="Existing recommendation with optional missing pack size.",
        generated_by="test",
    )
    db_session.add(recommendation)
    db_session.commit()

    response = client.get("/recommendations/cleanup-candidates")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_candidates"] == 0
    assert payload["candidates"] == []


def test_cleanup_candidates_endpoint_reports_missing_supplier_and_lead_time(client, db_session):
    product = Product(name="Cleanup Blocked Product", current_stock=0)
    db_session.add(product)
    db_session.flush()
    db_session.add(
        Recommendation(
            product_id=product.id,
            recommended_qty=1,
            risk_level="medium",
            recommendation_type="reorder",
            status="pending_review",
            reason="Existing unsafe recommendation row.",
            generated_by="test",
        )
    )
    db_session.commit()

    response = client.get("/recommendations/cleanup-candidates")

    assert response.status_code == 200
    payload = response.json()
    candidate = payload["candidates"][0]
    assert candidate["purchase_readiness_status"] == "blocked"
    assert "missing supplier" in candidate["issues"]
    assert "missing lead time" in candidate["issues"]
    assert candidate["suggested_action"] == "update_after_supplier_fix"


def test_rejected_product_supplier_is_not_used_for_recommendation(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session, match_status="rejected")

    response = client.post(f"/recommendations/reorder/{product.id}")

    assert response.status_code == 201
    payload = response.json()
    assert payload["supplier_context_snapshot"]["mapping_source"] == "orderpro_product_supplier"
    assert payload["product_supplier_id"] is None


def test_accept_recommendation_changes_status(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)
    recommendation = create_recommendation(client, product.id)

    payload = accept_recommendation(client, recommendation["id"], reviewed_by="buyer")

    assert payload["status"] == "accepted"
    assert payload["reviewed_by"] == "buyer"
    assert payload["reviewed_at"] is not None


def test_reject_recommendation_changes_status_and_stores_reason(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)
    recommendation = create_recommendation(client, product.id)

    response = client.post(
        f"/recommendations/{recommendation['id']}/reject",
        json={"reviewed_by": "buyer", "rejected_reason": "Too early to reorder."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["reviewed_by"] == "buyer"
    assert payload["rejected_reason"] == "Too early to reorder."


def test_orderpro_recommendation_conversion_waits_for_purchase_order_refactor(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)
    recommendation = create_recommendation(client, product.id)
    accept_recommendation(client, recommendation["id"])

    response = client.post(f"/recommendations/{recommendation['id']}/convert-to-draft-po")

    assert response.status_code == 400
    assert response.json()["detail"] == "Recommendation does not have a ProductSupplier mapping."
    assert db_session.query(PurchaseOrder).count() == 0


def test_cannot_convert_rejected_recommendation(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)
    recommendation = create_recommendation(client, product.id)
    reject_response = client.post(
        f"/recommendations/{recommendation['id']}/reject",
        json={"rejected_reason": "No purchase needed."},
    )
    assert reject_response.status_code == 200

    response = client.post(f"/recommendations/{recommendation['id']}/convert-to-draft-po")

    assert response.status_code == 400
    assert response.json()["detail"] == "Only accepted recommendations can be converted to a draft purchase order."
    assert db_session.query(PurchaseOrder).count() == 0


def test_cannot_convert_pending_recommendation_without_acceptance(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)
    recommendation = create_recommendation(client, product.id)

    response = client.post(f"/recommendations/{recommendation['id']}/convert-to-draft-po")

    assert response.status_code == 400
    assert response.json()["detail"] == "Only accepted recommendations can be converted to a draft purchase order."
    assert db_session.query(PurchaseOrder).count() == 0


def test_list_and_get_recommendations(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)
    recommendation = create_recommendation(client, product.id)

    list_response = client.get("/recommendations")
    detail_response = client.get(f"/recommendations/{recommendation['id']}")

    assert list_response.status_code == 200
    assert [row["id"] for row in list_response.json()] == [recommendation["id"]]
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == recommendation["id"]
