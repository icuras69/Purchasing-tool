from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


SUPPLIER_SOURCE_OF_TRUTH_PRIORITY = (
    "products.supplier_id",
    "orderpro_supplier_identity",
    "legacy_product_supplier_fields",
    "product_suppliers_legacy_review",
    "supplier_name_text_display_only",
)


@dataclass(frozen=True)
class SupplierIdentityResolution:
    supplier: Any | None
    method: str | None
    status: str
    candidates: tuple[Any, ...] = ()
    reason: str | None = None


def clean_supplier_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def normalize_supplier_orderpro_id(value: Any) -> str | None:
    return clean_supplier_text(value)


def normalize_supplier_code(value: Any) -> str | None:
    text = clean_supplier_text(value)
    return text.upper() if text else None


def normalize_supplier_name(value: Any) -> str | None:
    text = clean_supplier_text(value)
    return text.lower() if text else None


def one_by_supplier_key(suppliers: Iterable[Any], field_name: str, normalizer) -> dict[str, Any]:
    by_key: dict[str, Any] = {}
    duplicate_keys: set[str] = set()
    for supplier in suppliers:
        key = normalizer(getattr(supplier, field_name, None))
        if not key:
            continue
        if key in by_key and getattr(by_key[key], "id", None) != getattr(supplier, "id", None):
            duplicate_keys.add(key)
            continue
        by_key[key] = supplier
    for key in duplicate_keys:
        by_key.pop(key, None)
    return by_key


def canonical_supplier(product: Any) -> Any | None:
    if getattr(product, "supplier_id", None) is None:
        return None
    return getattr(product, "supplier_record", None)


def supplier_display_label(product: Any, *, fallback_to_legacy_text: bool = True) -> str | None:
    supplier = canonical_supplier(product)
    if supplier is not None:
        return getattr(supplier, "name", None)
    if fallback_to_legacy_text:
        return clean_supplier_text(getattr(product, "supplier", None))
    return None


def supplier_context_source(product: Any) -> str:
    if canonical_supplier(product) is not None:
        return "products.supplier_id"
    if getattr(product, "supplier_id", None) is not None:
        return "products.supplier_id_missing_relationship"
    if clean_supplier_text(getattr(product, "supplier", None)):
        return "legacy_supplier_text_display_only"
    if getattr(product, "product_suppliers", None):
        return "product_suppliers_legacy_review"
    return "missing"


def resolve_supplier_identity(
    suppliers: Iterable[Any],
    *,
    orderpro_id: Any = None,
    orderpro_code: Any = None,
    name: Any = None,
) -> SupplierIdentityResolution:
    supplier_list = list(suppliers)
    steps = [
        ("orderpro_id", "orderpro_id", orderpro_id, normalize_supplier_orderpro_id),
        ("orderpro_code", "orderpro_code", orderpro_code, normalize_supplier_code),
    ]
    if not any(normalizer(value) for _, _, value, normalizer in steps):
        steps.append(("normalized_name", "normalized_name", name, normalize_supplier_name))
        steps.append(("name", "name", name, normalize_supplier_name))

    selected_supplier = None
    selected_method = None
    selected_candidates: tuple[Any, ...] = ()
    for method, field_name, value, normalizer in steps:
        key = normalizer(value)
        if not key:
            continue
        candidates = tuple(
            supplier
            for supplier in supplier_list
            if normalizer(getattr(supplier, field_name, None)) == key
        )
        if not candidates:
            continue
        if len(candidates) > 1:
            return SupplierIdentityResolution(
                supplier=None,
                method=method,
                status="ambiguous",
                candidates=candidates,
                reason=f"Multiple suppliers matched {method}.",
            )
        candidate = candidates[0]
        if selected_supplier is None:
            selected_supplier = candidate
            selected_method = method
            selected_candidates = candidates
            continue
        if getattr(selected_supplier, "id", None) != getattr(candidate, "id", None):
            return SupplierIdentityResolution(
                supplier=None,
                method="conflict",
                status="conflict",
                candidates=(selected_supplier, candidate),
                reason=f"{selected_method} and {method} matched different suppliers.",
            )

    if selected_supplier is None:
        return SupplierIdentityResolution(supplier=None, method=None, status="unmatched")
    return SupplierIdentityResolution(
        supplier=selected_supplier,
        method=selected_method,
        status="matched",
        candidates=selected_candidates,
    )
