from datetime import date, datetime, timezone

from app.models.orderpro_order import OrderProOrder, OrderProOrderItem
from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.purchase_order import PurchaseOrder
from app.models.recommendation import Recommendation
from app.models.supplier import Supplier
from app.models.usage_history import UsageHistory


def seed_recommendation_product(
    db_session,
    *,
    match_status: str = "matched",
    product_overrides: dict | None = None,
    mapping_overrides: dict | None = None,
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
    supplier = Supplier(
        name="Recommendation Supplier",
        normalized_name="RECOMMENDATION SUPPLIER",
        orderpro_id="supplier-1",
        orderpro_code="REC-SUP",
        lead_time_days=4,
    )
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
            date=date(2026, 1, 1),
            qty_used=2,
            net_qty=2,
            source_system="test",
        )
    )
    db_session.commit()
    return product, supplier, mapping


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
    assert response.json()["detail"] == "Product is missing an OrderPro supplier mapping."
    assert db_session.query(Recommendation).count() == 0


def test_legacy_supplier_text_creates_reviewable_recommendation_without_structured_mapping(client, db_session):
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
            date=date(2026, 1, 1),
            qty_used=2,
            net_qty=2,
            source_system="test",
        )
    )
    db_session.commit()

    payload = create_recommendation(client, product.id)

    assert payload["supplier_id"] is None
    assert payload["recommended_supplier_name"] == "Legacy Supplier Text"
    assert payload["supplier_context_snapshot"]["mapping_source"] == "legacy_product"
    assert payload["supplier_context_snapshot"]["needs_supplier_mapping"] is True
    assert "Structured OrderPro supplier mapping is missing" in payload["reason"]


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
