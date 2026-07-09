from types import SimpleNamespace

from app.services.product_identity import (
    CANONICAL_PRODUCT_IDENTITY_PRIORITY,
    normalize_barcode,
    normalize_product_code,
    normalize_product_name,
    resolve_product_identity,
)


def product(product_id: int, **fields):
    return SimpleNamespace(id=product_id, **fields)


def test_canonical_identity_priority_is_documented():
    assert CANONICAL_PRODUCT_IDENTITY_PRIORITY == (
        "orderpro_id",
        "sku_or_product_code",
        "barcode",
        "normalized_name",
        "local_product_id",
    )


def test_product_identity_normalizes_sku_code_barcode_and_name():
    assert normalize_product_code(" sku-1 ") == "SKU-1"
    assert normalize_product_code("abc  123") == "ABC 123"
    assert normalize_barcode(" 401 865-3020258.0 ") == "4018653020258"
    assert normalize_barcode("000000000000") is None
    assert normalize_product_name("  Product   Name  ") == "product name"


def test_identity_resolution_uses_name_only_when_stronger_identifiers_are_missing():
    by_name = product(1, orderpro_id="OP-1", orderpro_sku="SKU-1", barcode="BC1", name="Shared Name")
    other = product(2, orderpro_id="OP-2", orderpro_sku="SKU-2", barcode="BC2", name="Other")

    unmatched = resolve_product_identity([by_name, other], sku="missing", name="Shared Name")
    fallback = resolve_product_identity([by_name, other], name="Shared Name")

    assert unmatched.status == "unmatched"
    assert fallback.status == "matched"
    assert fallback.product is by_name
    assert fallback.method == "normalized_name"


def test_identity_resolution_prefers_orderpro_id_and_rejects_conflicting_identifiers():
    by_orderpro_id = product(1, orderpro_id="100", orderpro_sku="SKU-1", barcode="BC1", name="One")
    by_sku = product(2, orderpro_id="200", orderpro_sku="SKU-2", barcode="BC2", name="Two")

    result = resolve_product_identity(
        [by_orderpro_id, by_sku],
        orderpro_id="100",
        sku="sku-2",
    )

    assert result.status == "conflict"
    assert result.product is None
    assert {candidate.id for candidate in result.candidates} == {1, 2}


def test_identity_resolution_uses_barcode_after_sku_and_reports_ambiguous_barcode():
    first = product(1, orderpro_id=None, orderpro_sku=None, barcode="ABC-123", name="One")
    duplicate = product(2, orderpro_id=None, orderpro_sku=None, barcode="ABC123", name="Two")

    result = resolve_product_identity([first, duplicate], barcode="ABC 123")

    assert result.status == "ambiguous"
    assert result.method == "barcode"
    assert {candidate.id for candidate in result.candidates} == {1, 2}
