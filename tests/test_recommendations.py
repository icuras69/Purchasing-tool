from datetime import date

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
        "current_stock": 1,
        "safety_stock": 10,
        "min_order_qty": 1,
    }
    product_defaults.update(product_overrides or {})
    product = Product(**product_defaults)
    supplier = Supplier(name="Recommendation Supplier", normalized_name="RECOMMENDATION SUPPLIER")
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


def test_create_reorder_recommendation_for_product_with_valid_product_supplier(client, db_session):
    product, supplier, mapping = seed_recommendation_product(db_session)

    payload = create_recommendation(client, product.id)

    assert payload["product_id"] == product.id
    assert payload["supplier_id"] == supplier.id
    assert payload["product_supplier_id"] == mapping.id
    assert payload["recommendation_type"] == "reorder"
    assert payload["status"] == "pending_review"
    assert payload["recommended_quantity"] > 0
    assert payload["recommended_supplier_name"] == supplier.name
    assert payload["recommended_supplier_sku"] == mapping.supplier_sku
    assert payload["estimated_unit_cost"] == 5.0
    assert payload["currency"] == "USD"


def test_recommendation_stores_input_forecast_and_supplier_snapshots(client, db_session):
    product, _supplier, mapping = seed_recommendation_product(db_session)

    payload = create_recommendation(client, product.id)

    assert payload["input_snapshot"]["product"]["id"] == product.id
    assert payload["input_snapshot"]["product_supplier"]["id"] == mapping.id
    assert payload["forecast_snapshot"]["product_id"] == product.id
    assert payload["forecast_snapshot"]["recommended_qty"] > 0
    assert payload["supplier_context_snapshot"]["supplier_sku"] == mapping.supplier_sku
    assert payload["model_name"] is None
    assert payload["prompt_version"] is None
    assert payload["generated_by"] == "system"


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
    assert response.json()["detail"] == "Product does not have a valid ProductSupplier mapping."
    assert db_session.query(Recommendation).count() == 0


def test_rejected_product_supplier_is_not_used_for_recommendation(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session, match_status="rejected")

    response = client.post(f"/recommendations/reorder/{product.id}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Product does not have a valid ProductSupplier mapping."
    assert db_session.query(Recommendation).count() == 0


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


def test_convert_accepted_recommendation_to_draft_po(client, db_session):
    product, _supplier, mapping = seed_recommendation_product(db_session)
    recommendation = create_recommendation(client, product.id)
    accept_recommendation(client, recommendation["id"])

    response = client.post(f"/recommendations/{recommendation['id']}/convert-to-draft-po")

    assert response.status_code == 200
    payload = response.json()
    po = payload["purchase_order"]
    updated_recommendation = payload["recommendation"]
    assert po["status"] == "draft"
    assert po["approved_at"] is None
    assert po["issued_at"] is None
    assert po["received_at"] is None
    assert updated_recommendation["status"] == "converted_to_po"
    assert updated_recommendation["converted_purchase_order_id"] == po["id"]
    line = po["lines"][0]
    assert line["product_id"] == product.id
    assert line["product_supplier_id"] == mapping.id
    assert line["supplier_sku"] == mapping.supplier_sku
    assert line["supplier_product_name"] == mapping.supplier_product_name
    assert line["unit_cost"] == mapping.purchase_price
    assert line["currency"] == mapping.currency
    assert line["minimum_order_quantity"] == mapping.minimum_order_quantity
    assert line["pack_size"] == mapping.pack_size
    assert line["lead_time_days"] == mapping.lead_time_days


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
