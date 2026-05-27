from datetime import date

from app.models.product import Product
from app.models.product_master_item import ProductMasterItem
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier
from app.models.usage_history import UsageHistory
from app.services.forecasting import build_forecast, resolve_supplier_context


def supplier(name: str, lead_time_days: int | None = None) -> Supplier:
    return Supplier(
        name=name,
        normalized_name=name.lower().replace(" ", "_"),
        lead_time_days=lead_time_days,
    )


def product(name: str = "Test Product", **overrides) -> Product:
    defaults = {
        "name": name,
        "current_stock": 10,
        "safety_stock": 0,
        "lead_time_days": 0,
        "min_order_qty": 1,
    }
    defaults.update(overrides)
    return Product(**defaults)


def product_supplier(
    product_obj: Product,
    supplier_obj: Supplier,
    **overrides,
) -> ProductSupplier:
    defaults = {
        "product": product_obj,
        "supplier": supplier_obj,
        "supplier_sku": f"{supplier_obj.name[:3].upper()}-SKU",
        "supplier_product_name": f"{supplier_obj.name} Product",
        "purchase_price": 12.5,
        "currency": "USD",
        "is_preferred": False,
        "match_status": "matched",
        "match_method": "test_match",
    }
    defaults.update(overrides)
    return ProductSupplier(**defaults)


def add_usage(db_session, product_obj: Product, quantity: float = 1) -> None:
    db_session.add(
        UsageHistory(
            product=product_obj,
            date=date(2026, 1, 1),
            qty_used=quantity,
            net_qty=quantity,
            source_system="test",
        )
    )


def test_preferred_product_supplier_is_used(db_session):
    primary = supplier("Primary Supplier", lead_time_days=4)
    preferred = supplier("Preferred Supplier", lead_time_days=6)
    item = product()
    db_session.add_all(
        [
            item,
            product_supplier(item, primary, supplier_sku="PRIMARY"),
            product_supplier(item, preferred, supplier_sku="PREFERRED", is_preferred=True),
        ]
    )
    db_session.commit()

    context = resolve_supplier_context(item)

    assert context["mapping_source"] == "product_supplier"
    assert context["supplier_id"] == preferred.id
    assert context["supplier_name"] == "Preferred Supplier"
    assert context["matched_sku"] == "PREFERRED"
    assert context["supplier_sku"] == "PREFERRED"
    assert context["supplier_product_name"] == "Preferred Supplier Product"
    assert context["purchase_price"] == 12.5
    assert context["currency"] == "USD"
    assert context["match_status"] == "matched"
    assert context["match_method"] == "test_match"


def test_matched_product_supplier_is_used_when_none_preferred(db_session):
    weak_supplier = supplier("Weak Supplier", lead_time_days=3)
    matched_supplier = supplier("Matched Supplier", lead_time_days=5)
    item = product()
    db_session.add_all(
        [
            item,
            product_supplier(item, weak_supplier, supplier_sku="WEAK", match_status="review"),
            product_supplier(item, matched_supplier, supplier_sku="MATCHED", match_status="matched"),
        ]
    )
    db_session.commit()

    context = resolve_supplier_context(item)

    assert context["mapping_source"] == "product_supplier"
    assert context["supplier_name"] == "Matched Supplier"
    assert context["matched_sku"] == "MATCHED"


def test_product_supplier_lead_time_overrides_supplier_lead_time(db_session):
    supplier_obj = supplier("Mapped Supplier", lead_time_days=9)
    item = product(lead_time_days=12)
    db_session.add_all(
        [
            item,
            product_supplier(item, supplier_obj, lead_time_days=4),
        ]
    )
    db_session.commit()

    context = resolve_supplier_context(item)

    assert context["lead_time_days_used"] == 4
    assert context["lead_time_source"] == "product_supplier"


def test_supplier_lead_time_used_when_product_supplier_lead_time_missing(db_session):
    supplier_obj = supplier("Supplier Lead Time", lead_time_days=7)
    item = product(lead_time_days=12)
    db_session.add_all([item, product_supplier(item, supplier_obj, lead_time_days=None)])
    db_session.commit()

    context = resolve_supplier_context(item)

    assert context["lead_time_days_used"] == 7
    assert context["lead_time_source"] == "supplier_master"


def test_product_supplier_minimum_order_quantity_overrides_product_min_order_qty(db_session):
    supplier_obj = supplier("MOQ Supplier", lead_time_days=1)
    item = product(current_stock=1, min_order_qty=5)
    db_session.add_all(
        [
            item,
            product_supplier(item, supplier_obj, minimum_order_quantity=25, lead_time_days=1),
        ]
    )
    add_usage(db_session, item, quantity=1)
    db_session.commit()

    forecast = build_forecast(db_session, item)

    assert forecast["recommended_action"] == "order_now"
    assert forecast["recommended_qty"] == 25.0


def test_product_without_product_supplier_falls_back_to_product_master_item(db_session):
    supplier_obj = supplier("Master Item Supplier", lead_time_days=8)
    item = product()
    db_session.add_all([supplier_obj, item])
    db_session.flush()
    db_session.add(
        ProductMasterItem(
            sku="MASTER-SKU",
            name="Master Item Product",
            supplier=supplier_obj,
            product=item,
            supplier_name_raw="Master Item Supplier",
            cost_price=11.25,
            match_status="matched",
            match_method="sku",
        )
    )
    db_session.commit()

    context = resolve_supplier_context(item)

    assert context["mapping_source"] == "product_master_item"
    assert context["supplier_name"] == "Master Item Supplier"
    assert context["matched_sku"] == "MASTER-SKU"
    assert context["lead_time_days_used"] == 8


def test_product_without_mappings_falls_back_to_legacy_supplier(db_session):
    item = product(supplier="Legacy Supplier", lead_time_days=3, min_order_qty=6)
    db_session.add(item)
    db_session.commit()

    context = resolve_supplier_context(item)

    assert context["mapping_source"] == "legacy_product"
    assert context["supplier_name"] == "Legacy Supplier"
    assert context["lead_time_days_used"] == 3
    assert context["minimum_order_quantity_used"] == 6


def test_product_without_supplier_info_returns_missing_state(db_session):
    item = product()
    db_session.add(item)
    db_session.commit()

    context = resolve_supplier_context(item)

    assert context["mapping_source"] == "missing"
    assert context["supplier_name"] is None
    assert context["matched_sku"] is None
    assert context["lead_time_days_used"] == 0
    assert context["lead_time_source"] == "missing"
