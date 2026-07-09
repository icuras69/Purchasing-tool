from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


CANONICAL_PRODUCT_IDENTITY_PRIORITY = (
    "orderpro_id",
    "sku_or_product_code",
    "barcode",
    "normalized_name",
    "local_product_id",
)

BARCODE_PLACEHOLDERS = {
    "0",
    "00",
    "000",
    "0000",
    "000000",
    "000000000000",
    "0000000000000",
    "N/A",
    "NA",
    "NONE",
    "NULL",
    "UNKNOWN",
}


@dataclass(frozen=True)
class ProductIdentityResolution:
    product: Any | None
    method: str | None
    status: str
    candidates: tuple[Any, ...] = ()
    reason: str | None = None


def clean_identity_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def normalize_orderpro_id(value: Any) -> str | None:
    return clean_identity_text(value)


def normalize_product_code(value: Any) -> str | None:
    text = clean_identity_text(value)
    return text.upper() if text else None


def normalize_barcode(value: Any) -> str | None:
    text = clean_identity_text(value)
    if not text:
        return None
    text = re.sub(r"[\s-]+", "", text)
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".")[0]
    normalized = re.sub(r"[^A-Z0-9]+", "", text.upper())
    if not normalized or normalized in BARCODE_PLACEHOLDERS:
        return None
    return normalized


def normalize_product_name(value: Any) -> str | None:
    text = clean_identity_text(value)
    return text.lower() if text else None


def one_by_identity_key(products: Iterable[Any], field_name: str, normalizer) -> dict[str, Any]:
    by_key: dict[str, Any] = {}
    duplicate_keys: set[str] = set()
    for product in products:
        key = normalizer(getattr(product, field_name, None))
        if not key:
            continue
        if key in by_key and getattr(by_key[key], "id", None) != getattr(product, "id", None):
            duplicate_keys.add(key)
            continue
        by_key[key] = product
    for key in duplicate_keys:
        by_key.pop(key, None)
    return by_key


def identity_candidates(products: Iterable[Any], field_name: str, value: Any, normalizer) -> list[Any]:
    key = normalizer(value)
    if not key:
        return []
    return [product for product in products if normalizer(getattr(product, field_name, None)) == key]


def resolve_product_identity(
    products: Iterable[Any],
    *,
    orderpro_id: Any = None,
    sku: Any = None,
    product_code: Any = None,
    barcode: Any = None,
    name: Any = None,
) -> ProductIdentityResolution:
    product_list = list(products)
    steps = [
        ("orderpro_id", "orderpro_id", orderpro_id, normalize_orderpro_id),
        ("sku_or_product_code", "orderpro_sku", sku if sku is not None else product_code, normalize_product_code),
        ("barcode", "barcode", barcode, normalize_barcode),
    ]
    strong_identifier_supplied = any(normalizer(value) for _, _, value, normalizer in steps)
    if not strong_identifier_supplied:
        steps.append(("normalized_name", "name", name, normalize_product_name))

    selected_product = None
    selected_method = None
    selected_candidates: tuple[Any, ...] = ()
    for method, field_name, value, normalizer in steps:
        candidates = tuple(identity_candidates(product_list, field_name, value, normalizer))
        if not candidates:
            continue
        if len(candidates) > 1:
            return ProductIdentityResolution(
                product=None,
                method=method,
                status="ambiguous",
                candidates=candidates,
                reason=f"Multiple products matched {method}.",
            )
        candidate = candidates[0]
        if selected_product is None:
            selected_product = candidate
            selected_method = method
            selected_candidates = candidates
            continue
        if getattr(selected_product, "id", None) != getattr(candidate, "id", None):
            return ProductIdentityResolution(
                product=None,
                method="conflict",
                status="conflict",
                candidates=(selected_product, candidate),
                reason=f"{selected_method} and {method} matched different products.",
            )

    if selected_product is None:
        return ProductIdentityResolution(product=None, method=None, status="unmatched")
    return ProductIdentityResolution(
        product=selected_product,
        method=selected_method,
        status="matched",
        candidates=selected_candidates,
    )
