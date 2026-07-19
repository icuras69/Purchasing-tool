from datetime import date

from app.models.product import Product
from app.models.product_pack_rule import ProductPackRule
from app.models.purchase_order import PurchaseOrder
from app.models.supplier import Supplier
from app.models.usage_history import UsageHistory
from app.services.forecasting import build_forecast
from app.services.pack_rules import round_required_quantity
from app.services.purchase_order_drafting import snapshot_purchase_order_line_from_product


RECENT_DEMAND_DATE = date(2026, 7, 1)


def pack_rule(
    *,
    multiple: float,
    rule_name: str = "Test rule",
    pack_type: str | None = "pallet",
    units_per_box: float | None = None,
    units_per_pallet: float | None = None,
) -> ProductPackRule:
    return ProductPackRule(
        rule_name=rule_name,
        order_multiple=multiple,
        pack_type=pack_type,
        units_per_box=units_per_box,
        units_per_pallet=units_per_pallet,
        is_active=True,
    )


def seed_forecast_product(db_session, *, raw_quantity: float, order_multiple: float) -> Product:
    supplier = Supplier(
        name=f"Pack Rule Supplier {raw_quantity}",
        normalized_name=f"PACK RULE SUPPLIER {raw_quantity}",
        orderpro_id=f"pack-rule-supplier-{raw_quantity}",
        orderpro_code=f"PRS-{raw_quantity}",
        lead_time_days=1,
    )
    product = Product(
        name=f"Pack Rule Product {raw_quantity}",
        orderpro_sku=f"PACK-{raw_quantity}",
        source_system="orderpro",
        current_stock=0,
        safety_stock=0,
        min_order_qty=1,
        lead_time_days=1,
        cost_price=2.5,
    )
    db_session.add_all([supplier, product])
    db_session.flush()
    product.supplier_id = supplier.id
    rule = ProductPackRule(
        product_id=product.id,
        supplier_id=supplier.id,
        canonical_sku=product.orderpro_sku,
        rule_name="Uniblock default",
        order_multiple=order_multiple,
        pack_type="pallet",
        units_per_pallet=order_multiple,
        is_active=True,
        source_note="Smoke pack rule",
    )
    db_session.add_all(
        [
            rule,
            UsageHistory(
                product_id=product.id,
                date=RECENT_DEMAND_DATE,
                qty_used=raw_quantity,
                net_qty=raw_quantity,
                source_system="pack-rule-test",
            ),
        ]
    )
    db_session.commit()
    return product


def test_pack_rounding_acceptance_examples():
    cases = [
        (57, pack_rule(multiple=56, rule_name="Uniblock default", pack_type="pallet", units_per_pallet=56), 112),
        (13, pack_rule(multiple=12, rule_name="35kg High Energy Sheep", pack_type="pallet", units_per_pallet=12), 24),
        (71, pack_rule(multiple=70, rule_name="Equine 12kg Buckets", pack_type="pallet", units_per_pallet=70), 140),
        (43, pack_rule(multiple=42, rule_name="Jakoti", pack_type="box", units_per_box=42), 84),
        (
            9,
            pack_rule(
                multiple=8,
                rule_name="Himalayan Salt Rope Licks 1.5-2.0kg",
                pack_type="box",
                units_per_box=8,
                units_per_pallet=560,
            ),
            16,
        ),
        (
            7,
            pack_rule(
                multiple=6,
                rule_name="Himalayan Salt Rope Licks 2.5-3.5kg",
                pack_type="box",
                units_per_box=6,
                units_per_pallet=420,
            ),
            12,
        ),
    ]

    for raw_quantity, rule, expected_quantity in cases:
        rounded = round_required_quantity(raw_required_quantity=raw_quantity, rule=rule)
        assert rounded.final_quantity == expected_quantity
        assert rounded.raw_required_quantity == raw_quantity
        assert rounded.order_multiple == rule.order_multiple


def test_zero_raw_quantity_creates_no_order_recommendation():
    rounded = round_required_quantity(raw_required_quantity=0, rule=pack_rule(multiple=56))

    assert rounded.final_quantity == 0
    assert rounded.display == "0 units"


def test_missing_pack_rule_defaults_to_one_and_warns():
    rounded = round_required_quantity(raw_required_quantity=9, rule=None)

    assert rounded.final_quantity == 9
    assert rounded.order_multiple == 1
    assert rounded.rule_source == "default_order_multiple"
    assert rounded.warnings == ["No active pack rule configured; order multiple defaults to 1."]


def test_forecast_uses_active_product_pack_rule_after_raw_shortage(db_session):
    product = seed_forecast_product(db_session, raw_quantity=57, order_multiple=56)

    forecast = build_forecast(db_session, product)

    assert forecast["raw_required_quantity"] == 57
    assert forecast["recommended_qty"] == 112
    assert forecast["order_multiple"] == 56
    assert forecast["pack_rule_name"] == "Uniblock default"
    assert forecast["pack_rule_display"] == "112 units = 2 pallets (56 each)"
    assert forecast["pack_rounding_explanation"] == "57 raw -> 112 final using 56 order multiple"


def test_purchase_order_line_snapshot_keeps_pack_rule_context(db_session):
    product = seed_forecast_product(db_session, raw_quantity=43, order_multiple=42)
    po = PurchaseOrder(supplier_id=product.supplier_id, status="draft")
    db_session.add(po)
    db_session.flush()

    line = snapshot_purchase_order_line_from_product(po, product, 84, notes="Drafted from accepted recommendation.")

    assert line.quantity == 84
    assert line.pack_size == 42
    assert "Pack rule: 84 raw -> 84 final using 42 order multiple" in line.notes
    assert "84 units = 2 pallets (42 each)" in line.notes
