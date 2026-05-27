from app.models.product import Product
from app.models.product_master_item import ProductMasterItem
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier


def supplier(name: str, lead_time_days: int | None = None) -> Supplier:
    return Supplier(
        name=name,
        normalized_name=name.lower().replace(" ", "_"),
        lead_time_days=lead_time_days,
    )


def product(name: str = "Forecast Product", **overrides) -> Product:
    defaults = {
        "name": name,
        "current_stock": 10,
        "safety_stock": 0,
        "lead_time_days": 0,
        "min_order_qty": 1,
    }
    defaults.update(overrides)
    return Product(**defaults)


def get_forecast(client, product_id: int) -> dict:
    response = client.get(f"/products/{product_id}/forecast")
    assert response.status_code == 200
    return response.json()


def test_forecast_response_includes_supplier_context_for_preferred_product_supplier(
    client,
    db_session,
):
    supplier_obj = supplier("Preferred Supplier", lead_time_days=6)
    item = product()
    db_session.add_all(
        [
            item,
            ProductSupplier(
                product=item,
                supplier=supplier_obj,
                supplier_sku="PREF-SKU",
                supplier_product_name="Preferred Supplier Product",
                purchase_price=12.75,
                currency="USD",
                minimum_order_quantity=4,
                lead_time_days=3,
                is_preferred=True,
                match_status="matched",
                match_method="sku",
            ),
        ]
    )
    db_session.commit()

    forecast = get_forecast(client, item.id)
    context = forecast["supplier_context"]

    assert forecast["product_id"] == item.id
    assert "supplier_name" in forecast
    assert "matched_sku" in forecast
    assert "lead_time_days_used" in forecast
    assert "recommended_qty" in forecast
    assert context == {
        "supplier_id": supplier_obj.id,
        "supplier_name": "Preferred Supplier",
        "supplier_sku": "PREF-SKU",
        "supplier_product_name": "Preferred Supplier Product",
        "purchase_price": 12.75,
        "currency": "USD",
        "lead_time_days": 3,
        "lead_time_source": "product_supplier",
        "minimum_order_quantity": 4.0,
        "moq_source": "product_supplier",
        "match_status": "matched",
        "match_method": "sku",
        "mapping_source": "product_supplier",
        "has_supplier_mapping": True,
        "needs_supplier_mapping": False,
    }


def test_forecast_response_uses_product_master_item_context_when_falling_back(
    client,
    db_session,
):
    supplier_obj = supplier("Master Supplier", lead_time_days=7)
    item = product(min_order_qty=2)
    db_session.add_all([supplier_obj, item])
    db_session.flush()
    db_session.add(
        ProductMasterItem(
            sku="MASTER-SKU",
            name="Master Item Name",
            supplier=supplier_obj,
            product=item,
            supplier_name_raw="Master Supplier",
            cost_price=9.25,
            match_status="matched",
            match_method="import_match",
        )
    )
    db_session.commit()

    context = get_forecast(client, item.id)["supplier_context"]

    assert context["mapping_source"] == "product_master_item"
    assert context["supplier_id"] == supplier_obj.id
    assert context["supplier_name"] == "Master Supplier"
    assert context["supplier_sku"] == "MASTER-SKU"
    assert context["supplier_product_name"] == "Master Item Name"
    assert context["purchase_price"] == 9.25
    assert context["lead_time_days"] == 7
    assert context["minimum_order_quantity"] == 2.0
    assert context["moq_source"] == "product_record"
    assert context["has_supplier_mapping"] is True
    assert context["needs_supplier_mapping"] is False


def test_forecast_response_uses_legacy_product_context_when_no_mapping_exists(
    client,
    db_session,
):
    item = product(
        name="Legacy Forecast Product",
        supplier="Legacy Supplier",
        lead_time_days=5,
        min_order_qty=3,
    )
    db_session.add(item)
    db_session.commit()

    context = get_forecast(client, item.id)["supplier_context"]

    assert context["mapping_source"] == "legacy_product"
    assert context["supplier_name"] == "Legacy Supplier"
    assert context["supplier_sku"] is None
    assert context["lead_time_days"] == 5
    assert context["lead_time_source"] == "product_record"
    assert context["minimum_order_quantity"] == 3.0
    assert context["moq_source"] == "product_record"
    assert context["has_supplier_mapping"] is True
    assert context["needs_supplier_mapping"] is False


def test_forecast_response_returns_missing_supplier_context_when_no_supplier_data(
    client,
    db_session,
):
    item = product(name="Missing Supplier Forecast Product")
    db_session.add(item)
    db_session.commit()

    context = get_forecast(client, item.id)["supplier_context"]

    assert context["mapping_source"] == "missing"
    assert context["supplier_id"] is None
    assert context["supplier_name"] is None
    assert context["supplier_sku"] is None
    assert context["supplier_product_name"] is None
    assert context["purchase_price"] is None
    assert context["currency"] is None
    assert context["lead_time_days"] == 0
    assert context["lead_time_source"] == "missing"
    assert context["minimum_order_quantity"] == 0.0
    assert context["moq_source"] == "missing"
    assert context["match_status"] is None
    assert context["match_method"] is None
    assert context["has_supplier_mapping"] is False
    assert context["needs_supplier_mapping"] is True
