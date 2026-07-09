from types import SimpleNamespace

from app.services.supplier_identity import (
    SUPPLIER_SOURCE_OF_TRUTH_PRIORITY,
    normalize_supplier_code,
    normalize_supplier_name,
    resolve_supplier_identity,
    supplier_context_source,
    supplier_display_label,
)


def supplier(supplier_id: int, **fields):
    return SimpleNamespace(id=supplier_id, **fields)


def product(**fields):
    defaults = {
        "supplier_id": None,
        "supplier_record": None,
        "supplier": None,
        "product_suppliers": [],
    }
    defaults.update(fields)
    return SimpleNamespace(**defaults)


def test_supplier_source_of_truth_priority_is_documented():
    assert SUPPLIER_SOURCE_OF_TRUTH_PRIORITY == (
        "products.supplier_id",
        "orderpro_supplier_identity",
        "legacy_product_supplier_fields",
        "product_suppliers_legacy_review",
        "supplier_name_text_display_only",
    )


def test_supplier_code_and_name_normalization():
    assert normalize_supplier_code(" sup-1 ") == "SUP-1"
    assert normalize_supplier_name("  Acme   Supplies  ") == "acme supplies"


def test_supplier_display_prefers_product_supplier_record_over_legacy_text():
    canonical = supplier(1, name="OrderPro Supplier", orderpro_code="OP")
    item = product(
        supplier_id=canonical.id,
        supplier_record=canonical,
        supplier="Legacy Supplier",
    )

    assert supplier_display_label(item) == "OrderPro Supplier"
    assert supplier_context_source(item) == "products.supplier_id"


def test_legacy_supplier_text_is_display_only_when_no_supplier_id():
    item = product(supplier="Legacy Supplier")

    assert supplier_display_label(item) == "Legacy Supplier"
    assert supplier_display_label(item, fallback_to_legacy_text=False) is None
    assert supplier_context_source(item) == "legacy_supplier_text_display_only"


def test_supplier_identity_resolution_detects_conflicting_orderpro_identifiers():
    by_id = supplier(1, orderpro_id="100", orderpro_code="SUP1", normalized_name="one", name="One")
    by_code = supplier(2, orderpro_id="200", orderpro_code="SUP2", normalized_name="two", name="Two")

    result = resolve_supplier_identity([by_id, by_code], orderpro_id="100", orderpro_code="sup2")

    assert result.status == "conflict"
    assert result.supplier is None
    assert {candidate.id for candidate in result.candidates} == {1, 2}


def test_supplier_identity_resolution_uses_name_only_without_stronger_identifiers():
    by_name = supplier(1, orderpro_id="100", orderpro_code="SUP1", normalized_name="acme ltd", name="Acme Ltd")

    with_strong_miss = resolve_supplier_identity([by_name], orderpro_code="missing", name="Acme Ltd")
    fallback = resolve_supplier_identity([by_name], name=" Acme   Ltd ")

    assert with_strong_miss.status == "unmatched"
    assert fallback.status == "matched"
    assert fallback.supplier is by_name
    assert fallback.method == "normalized_name"
