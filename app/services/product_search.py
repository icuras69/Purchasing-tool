from __future__ import annotations

from typing import Any, Iterable


def normalize_search_query(search: str | None) -> str:
    return " ".join((search or "").strip().lower().split())


def parse_exact_product_id(search: str | None) -> int | None:
    normalized = normalize_search_query(search)
    if normalized.isdigit():
        try:
            return int(normalized)
        except ValueError:
            return None
    return None


def filter_product_rows_by_search(
    rows: Iterable[dict[str, Any]],
    search: str | None,
    *,
    id_field: str = "product_id",
    exact_fields: tuple[str, ...] = ("sku", "orderpro_sku", "barcode", "supplier_sku"),
    partial_fields: tuple[str, ...] = ("product_name", "name", "description"),
    supplier_fields: tuple[str, ...] = ("supplier_name", "supplier_code"),
) -> list[dict[str, Any]]:
    row_list = list(rows)
    normalized = normalize_search_query(search)
    if not normalized:
        return row_list

    exact_product_id = parse_exact_product_id(normalized)
    if exact_product_id is not None:
        exact_id_rows = [row for row in row_list if _coerce_int(row.get(id_field)) == exact_product_id]
        if exact_id_rows:
            return exact_id_rows

    exact_matches = [
        row
        for row in row_list
        if any(normalize_search_query(_string(row.get(field))) == normalized for field in exact_fields)
    ]
    if exact_matches:
        return exact_matches

    return [
        row
        for row in row_list
        if normalized
        in " ".join(
            normalize_search_query(_string(row.get(field)))
            for field in (*partial_fields, *supplier_fields)
        )
    ]


def _string(value: Any) -> str:
    return "" if value is None else str(value)


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
