from datetime import date, datetime

from app.models.product import Product
from app.models.product_forecast_input_profile import ProductForecastInputProfile
from app.models.product_supplier import ProductSupplier
from app.models.recommendation import Recommendation
from app.models.supplier import Supplier
from app.models.usage_history import UsageHistory
from app.services.pack_size_audit import pack_size_audit


def make_supplier(db_session, name: str, *, lead_time_days: int = 4) -> Supplier:
    supplier = Supplier(
        name=name,
        normalized_name=name.upper(),
        orderpro_id=f"supplier-{name}",
        orderpro_code=f"SUP-{name[:8]}",
        lead_time_days=lead_time_days,
    )
    db_session.add(supplier)
    db_session.flush()
    return supplier


def make_product(
    db_session,
    supplier: Supplier | None,
    *,
    name: str = "Pack Audit Product",
    current_stock: float = 0,
    safety_stock: float = 5,
    min_order_qty: float = 1,
    cost_price: float | None = 5.0,
) -> Product:
    product = Product(
        name=name,
        orderpro_id=f"op-{name}",
        orderpro_sku=f"SKU-{name}",
        source_system="orderpro",
        supplier_id=supplier.id if supplier else None,
        supplier_sku=f"SUPSKU-{name}",
        current_stock=current_stock,
        safety_stock=safety_stock,
        min_order_qty=min_order_qty,
        cost_price=cost_price,
    )
    db_session.add(product)
    db_session.flush()
    return product


def add_mapping(
    db_session,
    product: Product,
    supplier: Supplier,
    *,
    pack_size: float | None,
    match_status: str = "confirmed",
    supplier_sku: str | None = None,
) -> ProductSupplier:
    mapping = ProductSupplier(
        product_id=product.id,
        supplier_id=supplier.id,
        supplier_sku=supplier_sku or f"MAP-{product.id}-{supplier.id}",
        pack_size=pack_size,
        minimum_order_quantity=product.min_order_qty,
        lead_time_days=supplier.lead_time_days,
        match_status=match_status,
        match_method="test",
    )
    db_session.add(mapping)
    db_session.flush()
    return mapping


def add_profile(db_session, product: Product, *, pack_size: float | None) -> ProductForecastInputProfile:
    now = datetime(2026, 7, 1)
    profile = ProductForecastInputProfile(
        product_id=product.id,
        cost_price=product.cost_price,
        cost_source="product_record" if product.cost_price is not None else "missing",
        cost_confidence="high" if product.cost_price is not None else "missing",
        lead_time_days=product.supplier_record.lead_time_days if product.supplier_record else None,
        lead_time_source="supplier_record" if product.supplier_record else "missing",
        lead_time_confidence="medium" if product.supplier_record else "missing",
        min_order_qty=product.min_order_qty,
        moq_source="product_record",
        pack_size=pack_size,
        pack_size_source="forecast_input_profile" if pack_size else "missing",
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
    db_session.flush()
    return profile


def add_usage(db_session, product: Product, *, usage_date: date = date(2026, 7, 1), qty: float = 2) -> UsageHistory:
    row = UsageHistory(
        product_id=product.id,
        date=usage_date,
        qty_used=qty,
        net_qty=qty,
        source_system="test",
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_pack_size_audit_counts_existing_profile_pack_sizes(client, db_session):
    supplier = make_supplier(db_session, "Profile Pack Supplier")
    product = make_product(db_session, supplier, name="Profile Pack")
    add_profile(db_session, product, pack_size=4)
    db_session.commit()

    response = client.get("/recommendations/pack-size-audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_products"] == 1
    assert payload["summary"]["products_missing_effective_pack_size"] == 0
    assert payload["summary"]["products_with_existing_profile_pack_size"] == 1
    assert payload["source_counts"]["product_forecast_input_profiles"]["populated"] == 1


def test_pack_size_audit_finds_safe_legacy_candidates(client, db_session):
    supplier = make_supplier(db_session, "Safe Pack Supplier")
    product = make_product(db_session, supplier, name="Safe Pack")
    add_mapping(db_session, product, supplier, pack_size=6, match_status="confirmed")
    db_session.commit()

    response = client.get("/recommendations/pack-size-audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["safe_candidate_count"] == 1
    assert payload["safe_candidates"][0]["product_id"] == product.id
    assert payload["safe_candidates"][0]["pack_size"] == 6


def test_pack_size_audit_reports_conflicting_legacy_pack_sizes(client, db_session):
    supplier = make_supplier(db_session, "Conflict Supplier")
    other_supplier = make_supplier(db_session, "Other Conflict Supplier")
    product = make_product(db_session, supplier, name="Conflict Pack")
    add_mapping(db_session, product, supplier, pack_size=6, match_status="confirmed", supplier_sku="C-1")
    add_mapping(db_session, product, other_supplier, pack_size=12, match_status="confirmed", supplier_sku="C-2")
    db_session.commit()

    response = client.get("/recommendations/pack-size-audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["conflict_count"] == 1
    assert payload["conflicts"][0]["product_id"] == product.id
    assert payload["conflicts"][0]["candidate_pack_sizes"] == [6.0, 12.0]


def test_rejected_legacy_supplier_mapping_is_not_safe_candidate(client, db_session):
    supplier = make_supplier(db_session, "Rejected Pack Supplier")
    product = make_product(db_session, supplier, name="Rejected Pack")
    add_mapping(db_session, product, supplier, pack_size=6, match_status="rejected")
    db_session.commit()

    response = client.get("/recommendations/pack-size-audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["safe_candidate_count"] == 0
    assert payload["summary"]["no_candidate_count"] == 1


def test_candidate_supplier_must_match_canonical_product_supplier(client, db_session):
    supplier = make_supplier(db_session, "Canonical Pack Supplier")
    other_supplier = make_supplier(db_session, "Mismatch Pack Supplier")
    product = make_product(db_session, supplier, name="Mismatch Pack")
    add_mapping(db_session, product, other_supplier, pack_size=6, match_status="confirmed")
    db_session.commit()

    response = client.get("/recommendations/pack-size-audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["safe_candidate_count"] == 0
    assert payload["summary"]["no_candidate_count"] == 1


def test_simulation_does_not_mark_stale_only_product_order_ready_after_pack_fix(client, db_session):
    supplier = make_supplier(db_session, "Stale Pack Supplier")
    product = make_product(db_session, supplier, name="Stale Pack", current_stock=0, safety_stock=0)
    add_mapping(db_session, product, supplier, pack_size=1, match_status="confirmed")
    add_usage(db_session, product, usage_date=date(2025, 1, 1), qty=2)
    db_session.commit()

    response = client.get("/recommendations/pack-size-audit")

    assert response.status_code == 200
    payload = response.json()
    summary = payload["recommendation_impact_simulation"]["summary"]
    item = payload["recommendation_impact_simulation"]["items"][0]
    assert summary["products_simulated"] == 1
    assert summary["would_become_order_ready"] == 0
    assert summary["stale_demand_still_needs_review"] == 1
    assert item["simulated_purchase_readiness"] == "needs_review"


def test_pack_size_audit_endpoint_is_read_only(client, db_session):
    supplier = make_supplier(db_session, "Read Only Pack Supplier")
    product = make_product(db_session, supplier, name="Read Only Pack")
    add_mapping(db_session, product, supplier, pack_size=6, match_status="confirmed")
    db_session.add(
        Recommendation(
            product_id=product.id,
            supplier_id=supplier.id,
            recommended_qty=2,
            risk_level="medium",
            recommendation_type="reorder",
            status="pending_review",
            reason="Existing row.",
            generated_by="test",
        )
    )
    db_session.commit()
    profile_count = db_session.query(ProductForecastInputProfile).count()
    recommendation_count = db_session.query(Recommendation).count()

    response = client.get("/recommendations/pack-size-audit")

    assert response.status_code == 200
    assert db_session.query(ProductForecastInputProfile).count() == profile_count
    assert db_session.query(Recommendation).count() == recommendation_count
    assert db_session.get(Product, product.id).forecast_input_profile is None


def test_pack_size_audit_helper_matches_endpoint(client, db_session):
    supplier = make_supplier(db_session, "Helper Pack Supplier")
    product = make_product(db_session, supplier, name="Helper Pack")
    add_mapping(db_session, product, supplier, pack_size=3, match_status="matched")
    db_session.commit()

    helper_payload = pack_size_audit(db_session)
    response = client.get("/recommendations/pack-size-audit")

    assert response.status_code == 200
    assert response.json()["summary"] == helper_payload["summary"]
