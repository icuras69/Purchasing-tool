from app.models.product import Product
from app.models.product_supplier_assignment_review import ProductSupplierAssignmentReview
from app.models.supplier import Supplier
from app.services.forecasting import build_forecast
from app.services.orderpro_product_supplier_export import (
    _match_product,
    apply_orderpro_product_supplier_export,
    normalize_export_row,
    plan_orderpro_product_supplier_export,
    read_export_rows,
)
from app.services.seasonality_backtesting import audit_product_forecast_inputs


def _write_csv(tmp_path, rows, headers=None):
    headers = headers or list(rows[0].keys())
    path = tmp_path / "orderpro_products.csv"
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(str(row.get(header, "")) for header in headers))
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _supplier(db_session, name="Export Supplier", orderpro_id="sup-1", orderpro_code="EXSUP"):
    supplier = Supplier(
        name=name,
        normalized_name=name.lower().replace(" ", "-"),
        orderpro_id=orderpro_id,
        orderpro_code=orderpro_code,
    )
    db_session.add(supplier)
    db_session.commit()
    return supplier


def _product(
    db_session,
    name="Export Product",
    orderpro_id="1001",
    sku="SKU-1001",
    barcode="111",
    supplier_id=None,
    source_system="orderpro",
    source_key=None,
):
    is_orderpro = source_system == "orderpro"
    product = Product(
        name=name,
        source_system=source_system,
        source_key=source_key,
        orderpro_id=orderpro_id if is_orderpro else None,
        orderpro_sku=sku if is_orderpro else None,
        barcode=barcode,
        supplier_id=supplier_id,
        current_stock=3,
        lead_time_days=0,
        min_order_qty=1,
    )
    db_session.add(product)
    db_session.commit()
    return product


def test_csv_column_normalization_works(tmp_path):
    path = _write_csv(
        tmp_path,
        [{"Product SKU": "ABC", "Supplier-Code": "SUP", "Supplier Product Code": "S-ABC"}],
        headers=["Product SKU", "Supplier-Code", "Supplier Product Code"],
    )

    row = read_export_rows(path)[0]
    normalized = normalize_export_row(row)

    assert normalized["sku"] == "ABC"
    assert normalized["supplier_code"] == "SUP"
    assert normalized["supplier_sku"] == "S-ABC"


def test_header_diagnostics_include_detected_mapping_and_invalid_reasons(db_session, tmp_path):
    path = _write_csv(
        tmp_path,
        [
            {"Product SKU": "ABC", "Supplier-Code": "SUP"},
            {"Product SKU": "", "Supplier-Code": "SUP"},
            {"Product SKU": "NO-SUP", "Supplier-Code": ""},
        ],
        headers=["Product SKU", "Supplier-Code"],
    )

    plan = plan_orderpro_product_supplier_export(db_session, path)

    assert plan.summary["detected_columns"] == ["product_sku", "supplier_code"]
    assert plan.summary["mapped_columns"]["sku"] == ["product_sku"]
    assert plan.summary["mapped_columns"]["supplier_code"] == ["supplier_code"]
    assert plan.summary["missing_required_columns"] == []
    assert plan.summary["invalid_row_reason_counts"]["missing_product_identity"] == 1
    assert plan.summary["invalid_row_reason_counts"]["missing_supplier_identity"] == 1


def test_product_matches_by_exact_orderpro_id(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session, orderpro_id="9001")
    path = _write_csv(tmp_path, [{"id": "9001", "supplier_code": supplier.orderpro_code}])

    plan = plan_orderpro_product_supplier_export(db_session, path)

    assert plan.summary["products_matched_by_orderpro_id"] == 1
    assert plan.rows[0]["product_id"] == product.id


def test_product_matches_by_exact_sku(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session, orderpro_id="9002", sku="SKU-MATCH")
    path = _write_csv(tmp_path, [{"sku": "sku-match", "supplier_code": supplier.orderpro_code}])

    plan = plan_orderpro_product_supplier_export(db_session, path)

    assert plan.summary["products_matched_by_sku"] == 1
    assert plan.rows[0]["product_id"] == product.id


def test_blank_and_source_key_sku_values_are_ignored_for_current_orderpro_products(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session, orderpro_id="9100", sku=None, source_key="SOURCE-KEY-IS-NOT-SKU")
    path = _write_csv(tmp_path, [{"sku": "SOURCE-KEY-IS-NOT-SKU", "supplier_code": supplier.orderpro_code}])

    plan = plan_orderpro_product_supplier_export(db_session, path)

    assert plan.rows[0]["product_id"] is None
    assert plan.summary["blank_orderpro_product_sku_count"] == 1
    assert plan.summary["duplicate_orderpro_sku_key_count"] == 0
    assert plan.summary["nonblank_orderpro_sku_key_count"] == 0
    assert db_session.query(ProductSupplierAssignmentReview).count() == 0
    assert db_session.get(Product, product.id).supplier_id is None


def test_blank_barcode_values_are_ignored_for_current_orderpro_products(db_session, tmp_path):
    supplier = _supplier(db_session)
    _product(db_session, orderpro_id="9100b", sku="HAS-SKU", barcode=" ")
    path = _write_csv(tmp_path, [{"barcode": " ", "supplier_code": supplier.orderpro_code}])

    plan = plan_orderpro_product_supplier_export(db_session, path)

    assert plan.summary["blank_orderpro_product_barcode_count"] == 1
    assert plan.summary["duplicate_orderpro_barcode_key_count"] == 0
    assert plan.summary["export_rows_with_blank_barcode"] == 1
    assert plan.summary["rows_invalid"] == 1


def test_sku_duplicate_globally_but_single_orderpro_product_matches(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session, orderpro_id="9101", sku="DUP-GLOBAL")
    _product(
        db_session,
        name="Legacy Duplicate",
        orderpro_id="legacy-unused",
        sku="DUP-GLOBAL",
        source_system="local",
        source_key="DUP-GLOBAL",
    )
    path = _write_csv(tmp_path, [{"sku": "DUP-GLOBAL", "supplier_code": supplier.orderpro_code}])

    plan = plan_orderpro_product_supplier_export(db_session, path)

    assert plan.summary["products_matched_by_sku"] == 1
    assert plan.summary["sku_global_duplicate_but_single_orderpro_match"] == 1
    assert plan.rows[0]["product_id"] == product.id
    assert plan.summary["sample_orderpro_sku_matches"][0]["product_id"] == product.id


def test_duplicate_sku_among_orderpro_products_does_not_auto_match(db_session, tmp_path):
    product_one = _product(db_session, orderpro_id="9102", sku="UNIQUE-ONE")
    product_two = _product(db_session, orderpro_id="9103", sku="UNIQUE-TWO")

    product, method, warning = _match_product(
        {"orderpro_product_id": None, "sku": "DUP-ORDERPRO", "barcode": None},
        {
            "by_orderpro_id": {},
            "orderpro_by_sku": {
                "DUP-ORDERPRO": [
                    {"product": product_one, "field": "product_orderpro_sku"},
                    {"product": product_two, "field": "product_orderpro_sku"},
                ]
            },
            "global_by_sku": {"DUP-ORDERPRO": [product_one, product_two]},
            "orderpro_unique_barcodes": {},
            "orderpro_duplicate_barcodes": set(),
            "global_barcode_groups": {},
        },
    )

    assert product is None
    assert method is None
    assert warning == "SKU matches multiple current OrderPro products."


def test_legacy_only_sku_match_is_reported_but_not_applied(db_session, tmp_path):
    supplier = _supplier(db_session)
    _product(
        db_session,
        name="Legacy Only Product",
        orderpro_id="legacy-unused",
        sku="LEGACY-ONLY",
        source_system="local",
        source_key="LEGACY-ONLY",
    )
    path = _write_csv(tmp_path, [{"sku": "LEGACY-ONLY", "supplier_code": supplier.orderpro_code}])

    plan = apply_orderpro_product_supplier_export(db_session, path, apply_suggestions=True)

    assert plan.summary["legacy_only_product_matches"] == 1
    assert plan.summary["products_not_matched"] == 1
    assert plan.summary["sample_legacy_only_matches"][0]["product_match_method"] == "legacy_only_sku"
    assert db_session.query(ProductSupplierAssignmentReview).count() == 0


def test_product_matches_by_unique_barcode_and_duplicate_barcode_does_not_match(db_session, tmp_path):
    supplier = _supplier(db_session)
    unique = _product(db_session, orderpro_id="9003", sku="UNIQUE", barcode="12345")
    _product(db_session, orderpro_id="9004", sku="DUP-1", barcode="999")
    _product(db_session, orderpro_id="9005", sku="DUP-2", barcode="999")
    path = _write_csv(
        tmp_path,
        [
            {"barcode": "12345", "supplier_code": supplier.orderpro_code},
            {"barcode": "999", "supplier_code": supplier.orderpro_code},
        ],
    )

    plan = plan_orderpro_product_supplier_export(db_session, path)

    assert plan.summary["products_matched_by_unique_barcode"] == 1
    assert plan.rows[0]["product_id"] == unique.id
    assert plan.rows[1]["product_id"] is None
    assert "Barcode matches multiple current OrderPro products." in plan.rows[1]["warnings"]


def test_duplicate_count_counts_unique_duplicate_keys_not_affected_products(db_session, tmp_path):
    supplier = _supplier(db_session)
    _product(db_session, orderpro_id="9103a", sku="BAR-DUP-A", barcode="SAME-BAR")
    _product(db_session, orderpro_id="9103b", sku="BAR-DUP-B", barcode="SAME-BAR")
    path = _write_csv(
        tmp_path,
        [
            {"barcode": "SAME-BAR", "supplier_code": supplier.orderpro_code},
            {"barcode": "SAME-BAR", "supplier_code": supplier.orderpro_code},
        ],
    )

    plan = plan_orderpro_product_supplier_export(db_session, path)

    assert plan.summary["duplicate_orderpro_barcode_key_count"] == 1
    assert plan.summary["barcode_duplicate_among_orderpro_products"] == 1
    assert plan.summary["rows_with_duplicate_orderpro_barcode_match"] == 2
    assert plan.summary["sample_duplicate_orderpro_sku_keys"] == []


def test_barcode_duplicate_globally_but_single_orderpro_product_matches(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session, orderpro_id="9104", sku="BAR-ORDERPRO", barcode="BAR123")
    _product(
        db_session,
        name="Legacy Barcode Duplicate",
        orderpro_id="legacy-unused",
        sku="LEGACY-BAR",
        barcode="BAR123",
        source_system="local",
        source_key="LEGACY-BAR",
    )
    path = _write_csv(tmp_path, [{"barcode": "BAR123", "supplier_code": supplier.orderpro_code}])

    plan = plan_orderpro_product_supplier_export(db_session, path)

    assert plan.summary["products_matched_by_unique_barcode"] == 1
    assert plan.summary["barcode_global_duplicate_but_single_orderpro_match"] == 1
    assert plan.rows[0]["product_id"] == product.id
    assert plan.summary["sample_orderpro_barcode_matches"][0]["product_id"] == product.id


def test_duplicate_barcode_among_orderpro_products_does_not_auto_match(db_session, tmp_path):
    supplier = _supplier(db_session)
    _product(db_session, orderpro_id="9105", sku="BAR-DUP-1", barcode="BAR999")
    _product(db_session, orderpro_id="9106", sku="BAR-DUP-2", barcode="BAR999")
    path = _write_csv(tmp_path, [{"barcode": "BAR999", "supplier_code": supplier.orderpro_code}])

    plan = plan_orderpro_product_supplier_export(db_session, path)

    assert plan.rows[0]["product_id"] is None
    assert plan.summary["barcode_duplicate_among_orderpro_products"] == 1
    assert "Barcode matches multiple current OrderPro products." in plan.rows[0]["warnings"]


def test_supplier_matches_by_code_orderpro_id_and_unique_name(db_session, tmp_path):
    code_supplier = _supplier(db_session, name="Code Supplier", orderpro_id="1", orderpro_code="CODE")
    id_supplier = _supplier(db_session, name="Id Supplier", orderpro_id="2", orderpro_code="IDSUP")
    name_supplier = _supplier(db_session, name="Unique Name Supplier", orderpro_id="3", orderpro_code="NAME")
    _product(db_session, orderpro_id="p1", sku="P1")
    _product(db_session, orderpro_id="p2", sku="P2")
    _product(db_session, orderpro_id="p3", sku="P3")
    path = _write_csv(
        tmp_path,
        [
            {"id": "p1", "supplier_code": code_supplier.orderpro_code},
            {"id": "p2", "supplier_id": id_supplier.orderpro_id},
            {"id": "p3", "supplier_name": name_supplier.name},
        ],
        headers=["id", "supplier_code", "supplier_id", "supplier_name"],
    )

    plan = plan_orderpro_product_supplier_export(db_session, path)

    assert plan.summary["suppliers_matched_by_code"] == 1
    assert plan.summary["suppliers_matched_by_orderpro_id"] == 1
    assert plan.summary["suppliers_matched_by_unique_name"] == 1
    assert plan.rows[2]["can_confirm_exact_code"] is False
    assert plan.rows[2]["classification"] == "suggestion"


def test_name_only_match_is_not_auto_confirmed(db_session, tmp_path):
    supplier = _supplier(db_session, name="Name Only Supplier")
    product = _product(db_session)
    path = _write_csv(tmp_path, [{"id": product.orderpro_id, "supplier_name": supplier.name}])

    plan = apply_orderpro_product_supplier_export(
        db_session,
        path,
        apply_suggestions=True,
        confirm_exact_code=True,
    )

    db_session.expire_all()
    assert plan.products_confirmed == 0
    assert db_session.get(Product, product.id).supplier_id is None
    assert db_session.query(ProductSupplierAssignmentReview).one().suggested_supplier_id == supplier.id


def test_dry_run_writes_nothing(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session)
    path = _write_csv(tmp_path, [{"id": product.orderpro_id, "supplier_code": supplier.orderpro_code}])

    plan_orderpro_product_supplier_export(db_session, path)

    assert db_session.query(ProductSupplierAssignmentReview).count() == 0
    assert db_session.get(Product, product.id).supplier_id is None


def test_apply_suggestions_creates_review_rows_only(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session)
    path = _write_csv(tmp_path, [{"id": product.orderpro_id, "supplier_code": supplier.orderpro_code}])

    plan = apply_orderpro_product_supplier_export(db_session, path, apply_suggestions=True)

    review = db_session.query(ProductSupplierAssignmentReview).one()
    assert plan.records_created == 1
    assert review.suggestion_source == "orderpro_product_export"
    assert review.suggested_supplier_id == supplier.id
    assert db_session.get(Product, product.id).supplier_id is None


def test_confirm_exact_code_updates_product_supplier_locally(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session)
    path = _write_csv(
        tmp_path,
        [{"id": product.orderpro_id, "supplier_code": supplier.orderpro_code, "supplier_sku": "SUP-SKU"}],
    )

    plan = apply_orderpro_product_supplier_export(
        db_session,
        path,
        apply_suggestions=True,
        confirm_exact_code=True,
    )

    db_session.expire_all()
    updated = db_session.get(Product, product.id)
    review = db_session.query(ProductSupplierAssignmentReview).one()
    assert plan.products_confirmed == 1
    assert updated.supplier_id == supplier.id
    assert updated.supplier_sku == "SUP-SKU"
    assert review.status == "confirmed"
    assert review.reviewed_by == "orderpro_product_export"


def test_confirm_exact_code_can_confirm_current_orderpro_barcode_match(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session, orderpro_id="9201", sku="BAR-CODE-CONFIRM", barcode="BAR-CONFIRM")
    path = _write_csv(tmp_path, [{"barcode": product.barcode, "supplier_code": supplier.orderpro_code}])

    plan = apply_orderpro_product_supplier_export(
        db_session,
        path,
        apply_suggestions=True,
        confirm_exact_code=True,
    )

    db_session.expire_all()
    assert plan.products_confirmed == 1
    assert db_session.get(Product, product.id).supplier_id == supplier.id


def test_confirm_exact_code_does_not_call_orderpro(db_session, tmp_path, monkeypatch):
    supplier = _supplier(db_session)
    product = _product(db_session)
    path = _write_csv(tmp_path, [{"id": product.orderpro_id, "supplier_code": supplier.orderpro_code}])

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("OrderPro client must not be used for export reconciliation.")

    monkeypatch.setattr("app.services.orderpro_client.OrderProClient.generic_get", fail_if_called)
    plan = apply_orderpro_product_supplier_export(
        db_session,
        path,
        apply_suggestions=True,
        confirm_exact_code=True,
    )

    assert plan.products_confirmed == 1


def test_existing_supplier_conflict_is_not_overwritten(db_session, tmp_path):
    existing = _supplier(db_session, name="Existing Supplier", orderpro_id="1", orderpro_code="OLD")
    suggested = _supplier(db_session, name="Suggested Supplier", orderpro_id="2", orderpro_code="NEW")
    product = _product(db_session, supplier_id=existing.id)
    path = _write_csv(tmp_path, [{"id": product.orderpro_id, "supplier_code": suggested.orderpro_code}])

    plan = apply_orderpro_product_supplier_export(
        db_session,
        path,
        apply_suggestions=True,
        confirm_exact_code=True,
    )

    db_session.expire_all()
    assert plan.summary["products_with_existing_supplier_conflict"] == 1
    assert db_session.get(Product, product.id).supplier_id == existing.id


def test_existing_same_supplier_is_idempotent(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session, supplier_id=supplier.id)
    path = _write_csv(tmp_path, [{"id": product.orderpro_id, "supplier_code": supplier.orderpro_code}])

    plan = apply_orderpro_product_supplier_export(
        db_session,
        path,
        apply_suggestions=True,
        confirm_exact_code=True,
    )

    assert plan.summary["products_with_existing_supplier_same"] == 1
    assert plan.products_confirmed == 0


def test_supplier_sku_is_stored_in_export_evidence(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session)
    path = _write_csv(tmp_path, [{"id": product.orderpro_id, "supplier_code": supplier.orderpro_code, "supplier_sku": "S-1"}])

    apply_orderpro_product_supplier_export(db_session, path, apply_suggestions=True)

    review = db_session.query(ProductSupplierAssignmentReview).one()
    assert review.evidence_summary["supplier_sku"] == "S-1"


def test_unmatched_product_and_supplier_rows_are_reported(db_session, tmp_path):
    _product(db_session, orderpro_id="known-product")
    _supplier(db_session, orderpro_code="KNOWN")
    path = _write_csv(
        tmp_path,
        [
            {"id": "unknown-product", "supplier_code": "KNOWN"},
            {"id": "known-product", "supplier_code": "UNKNOWN"},
        ],
    )

    plan = plan_orderpro_product_supplier_export(db_session, path)

    assert plan.summary["products_not_matched"] == 1
    assert plan.summary["suppliers_not_matched"] == 1
    assert plan.summary["sample_unmatched_products"][0]["product_name"] is None
    assert plan.summary["sample_unmatched_suppliers"][0]["supplier_name"] is None


def test_forecast_readiness_improves_after_exact_code_confirmation(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session)
    path = _write_csv(tmp_path, [{"sku": product.orderpro_sku, "supplier_code": supplier.orderpro_code}])

    before = audit_product_forecast_inputs(db_session, product)
    apply_orderpro_product_supplier_export(
        db_session,
        path,
        apply_suggestions=True,
        confirm_exact_code=True,
    )
    db_session.expire_all()
    after = audit_product_forecast_inputs(db_session, db_session.get(Product, product.id))

    assert "missing_supplier" in before["blocking_issues"]
    assert "missing_supplier" not in after["blocking_issues"]


def test_unconfirmed_export_suggestion_does_not_affect_forecast_supplier_context(db_session, tmp_path):
    supplier = _supplier(db_session)
    product = _product(db_session)
    path = _write_csv(tmp_path, [{"sku": product.orderpro_sku, "supplier_code": supplier.orderpro_code}])

    apply_orderpro_product_supplier_export(db_session, path, apply_suggestions=True)
    forecast = build_forecast(db_session, product)

    assert forecast["supplier_context"]["mapping_source"] == "missing"
    assert forecast["supplier_context"]["needs_supplier_mapping"] is True
