from app.models.product import Product
from app.models.product_master_item import ProductMasterItem
from app.models.product_supplier import ProductSupplier
from app.models.product_supplier_assignment_review import ProductSupplierAssignmentReview
from app.models.supplier import Supplier
from app.services.direct_supplier_repair import plan_direct_supplier_repair, save_direct_supplier_repair_report
from app.services.forecasting import build_forecast
from app.services.recommendations import create_reorder_recommendation_for_product


def supplier(name: str = "Christies", **overrides) -> Supplier:
    defaults = {
        "name": name,
        "normalized_name": name.lower().replace(" ", "_"),
        "orderpro_code": name.upper().replace(" ", "_"),
        "lead_time_days": 3,
        "is_active": True,
        "source_system": "orderpro",
    }
    defaults.update(overrides)
    return Supplier(**defaults)


def product(name: str = "Missing Supplier Product", **overrides) -> Product:
    defaults = {
        "name": name,
        "barcode": "10308",
        "source_key": f"source-{name}",
        "product_type": "inventory",
        "is_non_inventory": False,
        "current_stock": 0,
        "min_order_qty": 1,
        "lead_time_days": 0,
    }
    defaults.update(overrides)
    return Product(**defaults)


def add_product_supplier_mapping(
    db_session,
    product_obj: Product,
    supplier_obj: Supplier,
    **overrides,
) -> ProductSupplier:
    defaults = {
        "product": product_obj,
        "supplier": supplier_obj,
        "supplier_sku": "10308",
        "supplier_product_name": "Groom Professional Blo i200 Blaster UK Plug",
        "purchase_price": 114.13,
        "minimum_order_quantity": 2,
        "match_status": "matched",
        "match_method": "exact_barcode",
    }
    defaults.update(overrides)
    mapping = ProductSupplier(**defaults)
    db_session.add(mapping)
    return mapping


def add_master_item(
    db_session,
    product_obj: Product,
    supplier_obj: Supplier,
    **overrides,
) -> ProductMasterItem:
    defaults = {
        "product": product_obj,
        "supplier": supplier_obj,
        "sku": f"MI-{product_obj.id or product_obj.name}",
        "name": product_obj.name,
        "supplier_name_raw": supplier_obj.name,
        "cost_price": 114.13,
        "sales_price": 255.5,
        "match_status": "matched",
        "match_method": "exact_barcode",
    }
    defaults.update(overrides)
    item = ProductMasterItem(**defaults)
    db_session.add(item)
    return item


def test_product_with_one_trusted_product_supplier_mapping_is_promoted(db_session):
    supplier_obj = supplier()
    product_obj = product(min_order_qty=0)
    db_session.add_all([supplier_obj, product_obj])
    db_session.flush()
    add_product_supplier_mapping(db_session, product_obj, supplier_obj)
    db_session.commit()

    plan = plan_direct_supplier_repair(db_session, apply=True)
    db_session.refresh(product_obj)

    assert plan.safe_promotions == 1
    assert plan.products_updated == 1
    assert product_obj.supplier_id == supplier_obj.id
    assert product_obj.supplier_sku == "10308"
    assert product_obj.cost_price == 114.13
    assert product_obj.lead_time_days == 3
    assert product_obj.min_order_qty == 2


def test_product_with_one_trusted_product_master_item_mapping_is_promoted(db_session):
    supplier_obj = supplier("Master Supplier")
    product_obj = product("Master Linked Product", barcode="M-1")
    db_session.add_all([supplier_obj, product_obj])
    db_session.flush()
    add_master_item(db_session, product_obj, supplier_obj, sku="MASTER-SKU", match_method="exact_sku")
    db_session.commit()

    plan = plan_direct_supplier_repair(db_session, apply=True)
    db_session.refresh(product_obj)

    assert plan.safe_promotions == 1
    assert product_obj.supplier_id == supplier_obj.id
    assert product_obj.supplier_sku == "MASTER-SKU"
    assert product_obj.cost_price == 114.13
    assert product_obj.sell_price == 255.5


def test_matching_supplier_in_both_legacy_tables_is_promoted(db_session):
    supplier_obj = supplier("Shared Supplier")
    product_obj = product("Shared Evidence Product", barcode="SHARED")
    db_session.add_all([supplier_obj, product_obj])
    db_session.flush()
    add_product_supplier_mapping(db_session, product_obj, supplier_obj, supplier_sku="PS-SKU")
    add_master_item(db_session, product_obj, supplier_obj, sku="MI-SKU")
    db_session.commit()

    plan = plan_direct_supplier_repair(db_session, apply=True)
    db_session.refresh(product_obj)
    item = plan.items[0]

    assert plan.safe_promotions == 1
    assert product_obj.supplier_id == supplier_obj.id
    assert product_obj.supplier_sku == "PS-SKU"
    assert item.source_tables == ["product_master_items", "product_suppliers"]


def test_conflicting_supplier_ids_are_skipped(db_session):
    supplier_a = supplier("Supplier A")
    supplier_b = supplier("Supplier B")
    product_obj = product("Conflict Product", barcode="CONFLICT")
    db_session.add_all([supplier_a, supplier_b, product_obj])
    db_session.flush()
    add_product_supplier_mapping(db_session, product_obj, supplier_a)
    add_master_item(db_session, product_obj, supplier_b, sku="CONFLICT-MI")
    db_session.commit()

    plan = plan_direct_supplier_repair(db_session, apply=True)
    db_session.refresh(product_obj)

    assert plan.conflicts == 1
    assert plan.products_updated == 0
    assert product_obj.supplier_id is None
    assert plan.items[0].status == "conflict"


def test_no_candidate_and_untrusted_or_inactive_candidates_are_skipped(db_session):
    active_supplier = supplier("Active")
    inactive_supplier = supplier("Inactive", is_active=False)
    no_candidate = product("No Candidate", barcode="NO")
    untrusted = product("Untrusted", barcode="UNTRUSTED")
    inactive = product("Inactive Candidate", barcode="INACTIVE")
    db_session.add_all([active_supplier, inactive_supplier, no_candidate, untrusted, inactive])
    db_session.flush()
    add_product_supplier_mapping(
        db_session,
        untrusted,
        active_supplier,
        supplier_sku="UNTRUSTED",
        match_status="possible",
        match_method="fuzzy_name",
    )
    add_product_supplier_mapping(
        db_session,
        inactive,
        inactive_supplier,
        supplier_sku="INACTIVE",
    )
    db_session.commit()

    plan = plan_direct_supplier_repair(db_session, apply=True)

    assert plan.skipped_no_candidate == 1
    assert plan.skipped_untrusted_match == 1
    assert plan.skipped_inactive_supplier == 1
    assert plan.products_updated == 0


def test_existing_direct_supplier_is_not_overwritten(db_session):
    direct_supplier = supplier("Direct")
    legacy_supplier = supplier("Legacy")
    product_obj = product("Already Direct", barcode="DIRECT", supplier_record=direct_supplier, supplier_sku="DIRECT-SKU")
    db_session.add_all([direct_supplier, legacy_supplier, product_obj])
    db_session.flush()
    add_product_supplier_mapping(db_session, product_obj, legacy_supplier, supplier_sku="LEGACY-SKU")
    db_session.commit()

    plan = plan_direct_supplier_repair(db_session, apply=True)
    db_session.refresh(product_obj)

    assert plan.skipped_existing_supplier == 1
    assert product_obj.supplier_id == direct_supplier.id
    assert product_obj.supplier_sku == "DIRECT-SKU"


def test_dry_run_makes_no_database_writes(db_session):
    supplier_obj = supplier()
    product_obj = product()
    db_session.add_all([supplier_obj, product_obj])
    db_session.flush()
    add_product_supplier_mapping(db_session, product_obj, supplier_obj)
    db_session.commit()

    plan = plan_direct_supplier_repair(db_session, apply=False)
    db_session.refresh(product_obj)

    assert plan.safe_promotions == 1
    assert plan.products_updated == 0
    assert product_obj.supplier_id is None
    assert db_session.query(ProductSupplierAssignmentReview).count() == 0


def test_apply_fills_only_missing_commercial_fields(db_session):
    supplier_obj = supplier(lead_time_days=8)
    product_obj = product(
        "Existing Commercial Fields",
        barcode="EXISTING",
        supplier_sku="KEEP-SKU",
        cost_price=99.0,
        sell_price=199.0,
        lead_time_days=5,
        min_order_qty=4,
    )
    db_session.add_all([supplier_obj, product_obj])
    db_session.flush()
    add_product_supplier_mapping(
        db_session,
        product_obj,
        supplier_obj,
        supplier_sku="NEW-SKU",
        purchase_price=12.0,
        minimum_order_quantity=10,
    )
    add_master_item(db_session, product_obj, supplier_obj, sku="MASTER-EXISTING", sales_price=55.0)
    db_session.commit()

    plan_direct_supplier_repair(db_session, apply=True)
    db_session.refresh(product_obj)

    assert product_obj.supplier_id == supplier_obj.id
    assert product_obj.supplier_sku == "KEEP-SKU"
    assert product_obj.cost_price == 99.0
    assert product_obj.sell_price == 199.0
    assert product_obj.lead_time_days == 5
    assert product_obj.min_order_qty == 4


def test_review_record_is_created_and_updated(db_session):
    supplier_obj = supplier()
    product_obj = product()
    existing_review = ProductSupplierAssignmentReview(
        product=product_obj,
        status="needs_review",
        confidence_label="none",
        confidence_score=0,
    )
    db_session.add_all([supplier_obj, product_obj, existing_review])
    db_session.flush()
    add_product_supplier_mapping(db_session, product_obj, supplier_obj)
    db_session.commit()

    plan_direct_supplier_repair(db_session, apply=True)
    review = db_session.query(ProductSupplierAssignmentReview).one()

    assert review.status == "confirmed"
    assert review.reviewed_supplier_id == supplier_obj.id
    assert review.reviewed_by == "direct_supplier_repair"
    assert review.suggestion_source == "direct_supplier_repair"
    assert review.evidence_summary["source_tables"] == ["product_suppliers"]


def test_product_3020_style_case_promotes_and_unblocks_forecast_and_recommendation(db_session):
    supplier_obj = supplier("Christies", orderpro_code="CHRISTIES", lead_time_days=3)
    product_obj = product(
        id=3020,
        name="Blo i200 Single Motor Blower - UK Plug",
        barcode="10308",
        source_key="10308::BLOI200SINGLEMOTORBLOWERUKPLUG",
    )
    db_session.add_all([supplier_obj, product_obj])
    db_session.flush()
    add_product_supplier_mapping(
        db_session,
        product_obj,
        supplier_obj,
        supplier_sku="10308",
        purchase_price=114.13,
        match_status="matched",
        match_method="exact_barcode",
    )
    add_master_item(
        db_session,
        product_obj,
        supplier_obj,
        sku="10308",
        cost_price=114.13,
        sales_price=255.5,
        match_status="matched",
        match_method="exact_barcode",
    )
    db_session.commit()

    plan = plan_direct_supplier_repair(db_session, product_id=3020, apply=True)
    db_session.refresh(product_obj)

    forecast = build_forecast(db_session, product_obj)
    recommendation = create_reorder_recommendation_for_product(db_session, 3020)

    assert plan.safe_promotions == 1
    assert product_obj.supplier_id == supplier_obj.id
    assert product_obj.supplier_sku == "10308"
    assert product_obj.cost_price == 114.13
    assert product_obj.lead_time_days == 3
    assert forecast["supplier_context"]["supplier_id"] == supplier_obj.id
    assert forecast["supplier_context"]["supplier_name"] == "Christies"
    assert forecast["supplier_context"]["supplier_code"] == "CHRISTIES"
    assert forecast["supplier_context"]["has_supplier_mapping"] is True
    assert forecast["supplier_context"]["needs_supplier_mapping"] is False
    assert recommendation.supplier_id == supplier_obj.id
    assert recommendation.recommended_supplier_name == "Christies"


def test_save_report_writes_json_and_csv(tmp_path, db_session):
    supplier_obj = supplier()
    product_obj = product()
    db_session.add_all([supplier_obj, product_obj])
    db_session.flush()
    add_product_supplier_mapping(db_session, product_obj, supplier_obj)
    db_session.commit()
    plan = plan_direct_supplier_repair(db_session)

    paths = save_direct_supplier_repair_report(plan, output_dir=tmp_path, timestamp="20260622_120000")

    assert "json_report" in paths
    assert "csv_report" in paths
    assert (tmp_path / "direct_supplier_repair_dry_run_20260622_120000.json").exists()
    assert (tmp_path / "direct_supplier_repair_dry_run_20260622_120000.csv").exists()
