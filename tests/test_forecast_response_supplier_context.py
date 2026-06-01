from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier


def supplier(name: str, lead_time_days: int | None = None, **overrides) -> Supplier:
    defaults = {
        "name": name,
        "normalized_name": name.lower().replace(" ", "_"),
        "lead_time_days": lead_time_days,
    }
    defaults.update(overrides)
    return Supplier(**defaults)


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


def test_forecast_response_includes_orderpro_product_supplier_context(client, db_session):
    supplier_obj = supplier("OrderPro Supplier", lead_time_days=6, orderpro_code="OP-SUP")
    item = product(supplier_record=supplier_obj, supplier_sku="SUP-SKU", cost_price=12.75, min_order_qty=4)
    db_session.add(item)
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
        "supplier_name": "OrderPro Supplier",
        "supplier_code": "OP-SUP",
        "supplier_sku": "SUP-SKU",
        "supplier_product_name": None,
        "purchase_price": 12.75,
        "currency": None,
        "lead_time_days": 6,
        "lead_time_source": "supplier_record",
        "minimum_order_quantity": 4.0,
        "moq_source": "product_record",
        "match_status": None,
        "match_method": None,
        "mapping_source": "orderpro_product_supplier",
        "has_supplier_mapping": True,
        "needs_supplier_mapping": False,
    }


def test_forecast_response_does_not_use_legacy_product_supplier_mapping(client, db_session):
    orderpro_supplier = supplier("OrderPro Supplier", lead_time_days=6, orderpro_code="OP")
    legacy_mapping_supplier = supplier("Legacy Mapping Supplier", lead_time_days=1)
    item = product(supplier_record=orderpro_supplier, supplier_sku="ORDERPRO-SKU")
    db_session.add_all(
        [
            item,
            ProductSupplier(
                product=item,
                supplier=legacy_mapping_supplier,
                supplier_sku="PREF-SKU",
                is_preferred=True,
                match_status="matched",
            ),
        ]
    )
    db_session.commit()

    context = get_forecast(client, item.id)["supplier_context"]

    assert context["mapping_source"] == "orderpro_product_supplier"
    assert context["supplier_name"] == "OrderPro Supplier"
    assert context["supplier_sku"] == "ORDERPRO-SKU"


def test_forecast_response_uses_legacy_product_context_when_supplier_id_missing(client, db_session):
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
    assert context["supplier_code"] is None
    assert context["supplier_sku"] is None
    assert context["lead_time_days"] == 5
    assert context["lead_time_source"] == "product_record"
    assert context["minimum_order_quantity"] == 3.0
    assert context["moq_source"] == "product_record"
    assert context["has_supplier_mapping"] is False
    assert context["needs_supplier_mapping"] is True


def test_forecast_response_returns_missing_supplier_context_when_no_supplier_data(client, db_session):
    item = product(name="Missing Supplier Forecast Product")
    db_session.add(item)
    db_session.commit()

    context = get_forecast(client, item.id)["supplier_context"]

    assert context["mapping_source"] == "missing"
    assert context["supplier_id"] is None
    assert context["supplier_name"] is None
    assert context["supplier_code"] is None
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
