from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pandas as pd
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session, selectinload

from app.models.product import Product
from app.models.supplier import Supplier
from app.models.usage_history import UsageHistory
from app.services.forecast_input_reconciliation import evaluate_product_readiness
from app.services.product_search import filter_product_rows_by_search, normalize_search_query, parse_exact_product_id


SOURCE_SYSTEM = "demand_history_import"
YEAR_SHEET_RE = re.compile(r"^(19|20)\d{2}$")
CONTROL_PRODUCT_NAMES = {"SELECT CUSTOMER", "SELECT PRODUCT"}
SALES_REQUIRED_KEYS = {"date", "quantity"}
SALES_PRODUCT_KEYS = {"product_id", "orderpro_sku", "sku", "barcode", "product_name"}
MAX_HEADER_SCAN_ROWS = 25
STANDARD_SALES_COLUMNS = [
    "Name",
    "Barcode",
    "Description",
    "Batch",
    "Invoice",
    "Date",
    "Price",
    "Quantity",
    "VAT Rate",
    "Gross",
    "Code",
    "Sales Person",
    "Purchase Order",
    "Nett",
    "VAT",
]
SERVICE_ROW_TERMS = {
    "admin fee",
    "collection",
    "courier",
    "customs",
    "delivery",
    "discount",
    "dhl",
    "fed ex",
    "fedex",
    "free delivery",
    "free shipping",
    "fulfillment",
    "heavy item",
    "heavy item shipping",
    "heavy item surcharge",
    "logo digitisation",
    "packaging",
    "postage",
    "return",
    "return postage",
    "returns",
    "shipping",
    "sponsorship",
    "supply and deliver",
}
SERVICE_ROW_PATTERNS = [
    re.compile(r"\bfulfill?ment\b", re.IGNORECASE),
    re.compile(r"\badmin\s*fee\b", re.IGNORECASE),
    re.compile(r"\bcustoms\b", re.IGNORECASE),
    re.compile(r"\bshipping\b", re.IGNORECASE),
    re.compile(r"\bdelivery\b", re.IGNORECASE),
    re.compile(r"\bcollection\b", re.IGNORECASE),
    re.compile(r"\bdiscount\b", re.IGNORECASE),
    re.compile(r"\bpackaging\b", re.IGNORECASE),
    re.compile(r"\bsurcharge\b", re.IGNORECASE),
    re.compile(r"\breturns?\b", re.IGNORECASE),
    re.compile(r"\bpostage\b", re.IGNORECASE),
    re.compile(r"\bcourier\b", re.IGNORECASE),
    re.compile(r"\bdhl\b", re.IGNORECASE),
    re.compile(r"\bfed\s*ex\b", re.IGNORECASE),
    re.compile(r"\bfedex\b", re.IGNORECASE),
    re.compile(r"\blogo\s+digitis(?:ation|ation|ing)\b", re.IGNORECASE),
    re.compile(r"\bsupply\s+and\s+deliver\b", re.IGNORECASE),
]
PRODUCT_LOOKUP_COLUMN_CANDIDATES = {
    "old_code": ["old_code", "old code", "source_code", "source code", "legacy_code", "legacy code", "code"],
    "old_barcode": ["old_barcode", "old barcode", "source_barcode", "source barcode", "legacy_barcode", "legacy barcode", "barcode"],
    "old_description": [
        "old_description",
        "old description",
        "source_description",
        "source description",
        "legacy_description",
        "legacy description",
        "description",
        "product_name",
        "name",
    ],
    "product_id": ["product_id", "local_product_id", "current_product_id", "matched_product_id"],
    "orderpro_sku": ["orderpro_sku", "orderpro sku", "current_sku", "current sku", "sku"],
    "current_barcode": ["current_barcode", "current barcode", "orderpro_barcode", "orderpro barcode"],
    "current_name": ["current_name", "current product", "current_product_name", "orderpro_name", "orderpro product"],
}
DEMAND_COVERAGE_COLUMNS = [
    "product_id",
    "sku",
    "product_name",
    "supplier_id",
    "supplier_code",
    "supplier_name",
    "has_demand_history",
    "demand_row_count",
    "earliest_demand_date",
    "latest_demand_date",
    "months_covered",
    "total_units",
    "units_last_30_days",
    "units_last_90_days",
    "average_monthly_units",
    "return_units",
    "stale_demand",
    "gap_warnings",
    "readiness_status",
    "readiness_score",
    "demand_source",
]


@dataclass
class DemandImportPlan:
    summary: dict[str, Any]
    rows: list[dict[str, Any]]
    planned_usage_rows: list[dict[str, Any]]
    warnings: list[str]


@dataclass
class CsvExport:
    content: bytes
    filename: str
    content_type: str = "text/csv; charset=utf-8"


def inspect_demand_file(path: str | Path, *, sheets: list[str] | None = None, all_sheets: bool = False) -> dict[str, Any]:
    source_path = Path(path)
    rows, inspection = load_source_file(source_path, sheets=sheets, all_sheets=all_sheets)
    columns = sorted({key for row in rows for key in row["raw"].keys()})
    mapped = {name: find_column(columns, candidates) for name, candidates in COLUMN_CANDIDATES.items()}
    inspection.update(
        {
        "path": str(source_path),
        "filename": source_path.name,
        "extension": source_path.suffix.lower(),
        "rows": len(rows),
        "detected_columns": columns,
        "mapped_columns": mapped,
        "missing_required_columns": [
            key
            for key in ["date", "quantity"]
            if mapped.get(key) is None
        ],
        "has_product_identifier": any(mapped.get(key) for key in ["product_id", "orderpro_sku", "sku", "barcode", "product_name"]),
        }
    )
    return inspection


def plan_demand_import(
    db: Session,
    file_path: str | Path,
    *,
    source_system: str = SOURCE_SYSTEM,
    sheets: list[str] | None = None,
    all_sheets: bool = False,
    mapping_file: str | Path | None = None,
    replace_existing_source: bool = False,
) -> DemandImportPlan:
    source_path = Path(file_path)
    source_rows, inspection = load_source_file(source_path, sheets=sheets, all_sheets=all_sheets)
    normalized = normalize_demand_rows(source_rows, source_path.name)
    matched = match_demand_rows_to_products(db, normalized, source_path=source_path, mapping_file=mapping_file)
    validated = validate_demand_rows(matched)
    planned_usage_rows, duplicate_summary = build_planned_usage_rows(
        db,
        validated,
        source_system=source_system,
        ignore_existing=replace_existing_source,
    )
    summary = summarize_plan(source_path, validated, planned_usage_rows, duplicate_summary, inspection=inspection)
    return DemandImportPlan(summary=summary, rows=validated, planned_usage_rows=planned_usage_rows, warnings=summary["warnings"])


def apply_demand_import(
    db: Session,
    file_path: str | Path,
    *,
    reviewed_by: str | None = None,
    source_system: str = SOURCE_SYSTEM,
    sheets: list[str] | None = None,
    all_sheets: bool = False,
    mapping_file: str | Path | None = None,
    replace_existing_source: bool = False,
) -> DemandImportPlan:
    plan = plan_demand_import(
        db,
        file_path,
        source_system=source_system,
        sheets=sheets,
        all_sheets=all_sheets,
        mapping_file=mapping_file,
        replace_existing_source=replace_existing_source,
    )
    try:
        replaced_usage_rows = 0
        if replace_existing_source:
            affected_product_ids = sorted({row["product_id"] for row in plan.planned_usage_rows})
            if affected_product_ids:
                replaced_usage_rows = (
                    db.query(UsageHistory)
                    .filter(
                        UsageHistory.source_system == source_system,
                        UsageHistory.product_id.in_(affected_product_ids),
                    )
                    .delete(synchronize_session=False)
                )
        for row in plan.planned_usage_rows:
            db.add(
                UsageHistory(
                    product_id=row["product_id"],
                    date=row["date"],
                    qty_used=row["qty_used"],
                    qty_returned=row["qty_returned"],
                    net_qty=row["net_qty"],
                    gross_revenue=row["gross_revenue"],
                    source_system=source_system,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    plan.summary["mode"] = "apply"
    plan.summary["reviewed_by"] = reviewed_by
    plan.summary["inserted_usage_rows"] = len(plan.planned_usage_rows)
    plan.summary["replace_existing_source"] = replace_existing_source
    plan.summary["replaced_usage_rows"] = replaced_usage_rows
    return plan


def save_demand_report(plan: DemandImportPlan, *, report_dir: str | Path = "tmp/demand_history_import_reports") -> dict[str, str]:
    target = Path(report_dir)
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = target / f"demand_history_import_{stamp}.json"
    csv_path = target / f"demand_history_reconciliation_{stamp}.csv"
    excluded_path = target / f"demand_history_excluded_service_rows_{stamp}.csv"
    json_path.write_text(json.dumps({"summary": plan.summary, "rows": plan.rows}, default=str, indent=2), encoding="utf-8")

    fieldnames = [
        "source_sheet",
        "source_row_number",
        "match_status",
        "matched_product_id",
        "matched_product_name",
        "match_method",
        "match_confidence",
        "reason",
        "sku",
        "barcode",
        "product_name",
        "candidate_products",
        "source_identifier",
        "external_ref",
        "date",
        "quantity",
        "gross_revenue",
        "duplicate_key",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in plan.rows:
            writer.writerow({key: csv_safe(json.dumps(row.get(key), default=str) if key == "candidate_products" else row.get(key)) for key in fieldnames})
    excluded_fields = [
        "source_sheet",
        "source_row_number",
        "date",
        "sku",
        "barcode",
        "product_name",
        "matched_product_id",
        "matched_product_name",
        "exclusion_reason",
        "quantity",
        "gross_revenue",
    ]
    with excluded_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=excluded_fields)
        writer.writeheader()
        for row in plan.rows:
            if row.get("match_status") != "excluded_non_inventory":
                continue
            writer.writerow(
                {
                    "source_sheet": csv_safe(row.get("source_sheet")),
                    "source_row_number": row.get("source_row_number"),
                    "date": row.get("date"),
                    "sku": csv_safe(row.get("sku")),
                    "barcode": csv_safe(row.get("barcode")),
                    "product_name": csv_safe(row.get("product_name")),
                    "matched_product_id": row.get("matched_product_id"),
                    "matched_product_name": csv_safe(row.get("matched_product_name")),
                    "exclusion_reason": csv_safe(row.get("reason")),
                    "quantity": row.get("quantity"),
                    "gross_revenue": row.get("gross_revenue"),
                }
            )
    return {"json_report": str(json_path), "reconciliation_csv": str(csv_path), "excluded_service_rows_csv": str(excluded_path)}


def save_ambiguous_review_reports(plan: DemandImportPlan, *, report_dir: str | Path = "tmp/demand_history_import_reports") -> dict[str, str]:
    target = Path(report_dir)
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    review_path = target / f"demand_history_ambiguous_review_{stamp}.csv"
    grouped_path = target / f"demand_history_ambiguous_grouped_{stamp}.csv"

    grouped = grouped_ambiguity_rows(plan.rows)
    group_lookup = {
        ambiguity_group_key(row): row
        for row in grouped
    }
    review_fields = [
        "sheet_name",
        "source_row_number",
        "date",
        "source_code",
        "source_barcode",
        "source_description",
        "quantity",
        "invoice",
        "match_reason",
        "candidate_product_ids",
        "candidate_orderpro_skus",
        "candidate_product_names",
        "candidate_barcodes",
        "total_quantity_for_same_source_identifier",
        "row_count_for_same_source_identifier",
        "suggested_review_priority",
    ]
    with review_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=review_fields)
        writer.writeheader()
        for row in plan.rows:
            if row.get("match_status") not in {"ambiguous", "ambiguous_conflict"}:
                continue
            grouped_row = group_lookup.get(ambiguity_group_key(row), {})
            candidates = row.get("candidate_products", [])
            writer.writerow(
                {
                    "sheet_name": csv_safe(row.get("source_sheet")),
                    "source_row_number": row.get("source_row_number"),
                    "date": row.get("date"),
                    "source_code": csv_safe(row.get("sku")),
                    "source_barcode": csv_safe(row.get("barcode")),
                    "source_description": csv_safe(row.get("product_name")),
                    "quantity": row.get("quantity"),
                    "invoice": csv_safe(row.get("external_ref")),
                    "match_reason": csv_safe(row.get("reason")),
                    "candidate_product_ids": csv_safe(";".join(str(candidate.get("product_id")) for candidate in candidates)),
                    "candidate_orderpro_skus": csv_safe(";".join(str(candidate.get("orderpro_sku") or "") for candidate in candidates)),
                    "candidate_product_names": csv_safe(";".join(str(candidate.get("name") or "") for candidate in candidates)),
                    "candidate_barcodes": csv_safe(";".join(str(candidate.get("barcode") or "") for candidate in candidates)),
                    "total_quantity_for_same_source_identifier": grouped_row.get("total_quantity"),
                    "row_count_for_same_source_identifier": grouped_row.get("row_count"),
                    "suggested_review_priority": grouped_row.get("suggested_review_priority"),
                }
            )

    grouped_fields = [
        "source_code",
        "source_barcode",
        "source_description",
        "row_count",
        "total_quantity",
        "first_date",
        "last_date",
        "candidate_count",
        "candidate_product_ids",
        "candidate_skus",
        "candidate_names",
        "reason",
        "suggested_review_priority",
    ]
    with grouped_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=grouped_fields)
        writer.writeheader()
        for row in grouped:
            writer.writerow({key: csv_safe(row.get(key)) for key in grouped_fields})
    return {"ambiguous_review_csv": str(review_path), "ambiguous_grouped_csv": str(grouped_path)}


COLUMN_CANDIDATES = {
    "product_id": ["product_id", "local product id", "product id"],
    "orderpro_sku": ["orderpro_sku", "orderpro sku", "orderpro product sku"],
    "sku": ["sku", "product_sku", "product sku", "code"],
    "barcode": ["barcode", "ean", "upc"],
    "product_name": ["product_name", "product name", "description", "name", "item"],
    "date": ["date", "sale date", "order date", "txn_date", "transaction date"],
    "quantity": ["quantity", "qty", "qty_used", "units", "net_qty"],
    "gross_revenue": ["gross", "gross_revenue", "revenue", "total", "nett"],
    "unit_price": ["price", "unit_price", "unit price"],
    "external_ref": ["invoice", "order_number", "order number", "reference", "purchase order"],
}


def normalize_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def find_column(columns: list[str], candidates: list[str]) -> str | None:
    by_normalized = {normalize_header(column): column for column in columns}
    for candidate in candidates:
        if normalize_header(candidate) in by_normalized:
            return by_normalized[normalize_header(candidate)]
    return None


def read_source_rows(path: Path, *, sheets: list[str] | None = None, all_sheets: bool = False) -> list[dict[str, Any]]:
    rows, _inspection = load_source_file(path, sheets=sheets, all_sheets=all_sheets)
    return rows


def load_source_file(
    path: Path,
    *,
    sheets: list[str] | None = None,
    all_sheets: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Demand history file not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        rows = read_csv_rows(path)
        columns = sorted({key for row in rows for key in row["raw"].keys()})
        mapped = {name: find_column(columns, candidates) for name, candidates in COLUMN_CANDIDATES.items()}
        return rows, {
            "total_workbook_rows_scanned": len(rows),
            "sheets_included": ["csv"],
            "sheets_skipped": {},
            "sheet_inspection": {
                "csv": {
                    "rows_scanned": len(rows),
                    "header_row": 1,
                    "detected_columns": columns,
                    "mapped_columns": mapped,
                    "is_sales_data": has_sales_columns(mapped),
                    "skip_reason": None,
                }
            },
        }
    if suffix in {".xlsx", ".xlsm"}:
        return read_xlsx_rows(path, sheets=sheets, all_sheets=all_sheets)
    raise ValueError("Supported demand history formats are .csv and .xlsx.")


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [{"source_sheet": "csv", "source_row_number": index + 2, "raw": dict(row)} for index, row in enumerate(reader)]


def read_xlsx_rows(
    path: Path,
    *,
    sheets: list[str] | None = None,
    all_sheets: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        matrices = read_xlsx_sheet_matrices_with_pandas(path)
    except Exception:
        matrices = read_xlsx_sheet_matrices_without_openpyxl(path)
    return rows_from_xlsx_matrices(matrices, sheets=sheets, all_sheets=all_sheets)


def read_xlsx_sheet_matrices_with_pandas(path: Path) -> dict[str, list[list[Any]]]:
    frames = pd.read_excel(path, sheet_name=None, dtype=object, header=None)
    matrices: dict[str, list[list[Any]]] = {}
    for sheet, frame in frames.items():
        values = frame.where(pd.notna(frame), None).values.tolist()
        matrices[str(sheet)] = values
    return matrices


def read_xlsx_sheet_matrices_without_openpyxl(path: Path) -> dict[str, list[list[Any]]]:
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall("main:si", ns):
                shared_strings.append("".join(text.text or "" for text in item.findall(".//main:t", ns)))
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels
            if rel.attrib.get("Type", "").endswith("/worksheet")
        }
        matrices: dict[str, list[list[Any]]] = {}
        for sheet in workbook.findall("main:sheets/main:sheet", ns):
            sheet_name = sheet.attrib["name"]
            rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = rel_targets[rel_id]
            sheet_path = "xl/" + target.lstrip("/")
            root = ElementTree.fromstring(archive.read(sheet_path))
            parsed_rows: list[list[Any]] = []
            for row in root.findall(".//main:sheetData/main:row", ns):
                values: list[Any] = []
                for fallback_index, cell in enumerate(row.findall("main:c", ns)):
                    ref = cell.attrib.get("r", "")
                    index = excel_column_index(ref) if ref else fallback_index
                    while len(values) <= index:
                        values.append(None)
                    value = cell.find("main:v", ns)
                    text = value.text if value is not None else ""
                    if cell.attrib.get("t") == "inlineStr":
                        text = "".join(node.text or "" for node in cell.findall(".//main:t", ns))
                    if cell.attrib.get("t") == "s" and text != "":
                        text = shared_strings[int(text)]
                    values[index] = text
                parsed_rows.append(values)
            matrices[sheet_name] = parsed_rows
        return matrices


def rows_from_xlsx_matrices(
    matrices: dict[str, list[list[Any]]],
    *,
    sheets: list[str] | None = None,
    all_sheets: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    requested = {sheet.strip() for sheet in sheets or [] if sheet.strip()}
    rows: list[dict[str, Any]] = []
    sheet_inspection: dict[str, dict[str, Any]] = {}
    sheets_included: list[str] = []
    sheets_skipped: dict[str, str] = {}
    total_scanned = 0

    for sheet_name, matrix in matrices.items():
        total_scanned += len(matrix)
        header_index, detected_columns, mapped = detect_sales_header(matrix)
        inferred_header = False
        if header_index is None and YEAR_SHEET_RE.fullmatch(sheet_name.strip()) and looks_like_headerless_sales_sheet(matrix):
            header_index = -1
            detected_columns = STANDARD_SALES_COLUMNS
            mapped = {name: find_column(detected_columns, candidates) for name, candidates in COLUMN_CANDIDATES.items()}
            inferred_header = True
        skip_reason = sheet_skip_reason(sheet_name, header_index, mapped, requested=requested, all_sheets=all_sheets)
        is_sales_data = skip_reason is None
        sheet_inspection[sheet_name] = {
            "rows_scanned": len(matrix),
            "header_row": header_index + 1 if header_index is not None and header_index >= 0 else None,
            "inferred_header": inferred_header,
            "detected_columns": detected_columns,
            "mapped_columns": mapped,
            "is_sales_data": is_sales_data,
            "skip_reason": skip_reason,
        }
        if skip_reason is not None:
            sheets_skipped[sheet_name] = skip_reason
            continue
        sheets_included.append(sheet_name)
        headers = detected_columns
        data_start = (header_index + 1) if header_index is not None else 0
        for row_number, values in enumerate(matrix[data_start:], start=data_start + 1):
            raw = {header: values[index] if index < len(values) else None for index, header in enumerate(headers)}
            if row_is_blank(raw):
                continue
            rows.append({"source_sheet": sheet_name, "source_row_number": row_number, "raw": raw})

    return rows, {
        "total_workbook_rows_scanned": total_scanned,
        "sheets_included": sheets_included,
        "sheets_skipped": sheets_skipped,
        "sheet_inspection": sheet_inspection,
    }


def detect_sales_header(matrix: list[list[Any]]) -> tuple[int | None, list[str], dict[str, str | None]]:
    for index, values in enumerate(matrix[:MAX_HEADER_SCAN_ROWS]):
        columns = [clean_header_cell(value) for value in values]
        columns = [column for column in columns if column]
        if not columns:
            continue
        mapped = {name: find_column(columns, candidates) for name, candidates in COLUMN_CANDIDATES.items()}
        if has_sales_columns(mapped):
            return index, columns, mapped
    return None, [], {name: None for name in COLUMN_CANDIDATES}


def looks_like_headerless_sales_sheet(matrix: list[list[Any]]) -> bool:
    sample_rows = [row for row in matrix[:50] if len(row) >= 10 and not row_is_blank_by_values(row)]
    if not sample_rows:
        return False
    plausible = 0
    for row in sample_rows[:20]:
        date_value = row[4] if len(row) > 4 else None
        quantity_value = row[6] if len(row) > 6 else None
        identifier_value = first_present(
            row[1] if len(row) > 1 else None,
            row[2] if len(row) > 2 else None,
            row[9] if len(row) > 9 else None,
        )
        if parse_date(date_value) is not None and parse_float(quantity_value) is not None and clean_text(identifier_value):
            plausible += 1
    return plausible >= min(3, len(sample_rows))


def has_sales_columns(mapped: dict[str, str | None]) -> bool:
    return SALES_REQUIRED_KEYS.issubset({key for key, value in mapped.items() if value}) and any(
        mapped.get(key) for key in SALES_PRODUCT_KEYS
    )


def sheet_skip_reason(
    sheet_name: str,
    header_index: int | None,
    mapped: dict[str, str | None],
    *,
    requested: set[str],
    all_sheets: bool,
) -> str | None:
    if requested:
        if sheet_name not in requested:
            return "not_requested"
    elif not all_sheets and not YEAR_SHEET_RE.fullmatch(sheet_name.strip()):
        return "not_year_named_sales_sheet"
    if header_index is None or not has_sales_columns(mapped):
        return "missing_required_sales_columns"
    return None


def clean_header_cell(value: Any) -> str:
    text = clean_text(value)
    return text or ""


def row_is_blank(raw: dict[str, Any]) -> bool:
    return all(clean_text(value) is None for value in raw.values())


def row_is_blank_by_values(values: list[Any]) -> bool:
    return all(clean_text(value) is None for value in values)


def excel_column_index(ref: str) -> int:
    letters = re.match(r"([A-Z]+)", ref or "")
    if not letters:
        return 0
    value = 0
    for char in letters.group(1):
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value - 1


def normalize_demand_rows(source_rows: list[dict[str, Any]], source_file: str) -> list[dict[str, Any]]:
    columns = sorted({str(key) for row in source_rows for key in row["raw"].keys()})
    mapped = {name: find_column(columns, candidates) for name, candidates in COLUMN_CANDIDATES.items()}
    reinterpret_day_first_sheets = infer_day_first_excel_datetime_sheets(source_rows, mapped.get("date"))
    rows = []
    for item in source_rows:
        raw = item["raw"]
        quantity = parse_float(raw.get(mapped["quantity"])) if mapped.get("quantity") else None
        raw_date = raw.get(mapped["date"]) if mapped.get("date") else None
        reinterpret_day_first = item["source_sheet"] in reinterpret_day_first_sheets
        parsed_date = parse_date(
            raw_date,
            reinterpret_ambiguous_datetime_day_first=reinterpret_day_first,
        ) if mapped.get("date") else None
        product_id = parse_int(raw.get(mapped["product_id"])) if mapped.get("product_id") else None
        orderpro_sku = clean_text(raw.get(mapped["orderpro_sku"])) if mapped.get("orderpro_sku") else None
        sku = clean_text(raw.get(mapped["sku"])) if mapped.get("sku") else None
        barcode = normalize_barcode(raw.get(mapped["barcode"])) if mapped.get("barcode") else None
        product_name = clean_text(raw.get(mapped["product_name"])) if mapped.get("product_name") else None
        gross_revenue = parse_float(raw.get(mapped["gross_revenue"])) if mapped.get("gross_revenue") else 0.0
        source_identifier = first_present(product_id, orderpro_sku, sku, barcode, product_name)
        rows.append(
            {
                "source_file": source_file,
                "source_sheet": item["source_sheet"],
                "source_row_number": item["source_row_number"],
                "raw": raw,
                "product_id_input": product_id,
                "orderpro_sku": orderpro_sku,
                "normalized_orderpro_sku": normalize_token(orderpro_sku),
                "sku": sku,
                "normalized_sku": normalize_token(sku or orderpro_sku),
                "barcode": barcode,
                "normalized_barcode": normalize_token(barcode),
                "product_name": product_name,
                "normalized_name": normalize_name(product_name),
                "date": parsed_date,
                "date_reinterpreted_day_first": bool(
                    reinterpret_day_first and is_ambiguous_datetime_value(raw_date)
                ),
                "quantity": quantity,
                "gross_revenue": gross_revenue or 0.0,
                "external_ref": clean_text(raw.get(mapped["external_ref"])) if mapped.get("external_ref") else None,
                "source_identifier": source_identifier,
                "match_status": "unmatched",
                "matched_product_id": None,
                "match_method": None,
                "match_confidence": 0.0,
                "reason": None,
            }
        )
    return rows


def match_demand_rows_to_products(
    db: Session,
    rows: list[dict[str, Any]],
    *,
    source_path: Path | None = None,
    mapping_file: str | Path | None = None,
) -> list[dict[str, Any]]:
    products = db.query(Product).all()
    by_id = {product.id: product for product in products}
    by_orderpro_sku = candidate_map(products, lambda product: normalize_token(product.orderpro_sku))
    by_current_barcode = candidate_map(products, lambda product: normalize_barcode(product.barcode))
    by_name = candidate_map(products, lambda product: normalize_name(product.name))
    by_description = candidate_map(products, lambda product: normalize_name(product.description))
    by_legacy_name = candidate_map(products, lambda product: normalize_name(product.canonical_description))
    alias_index = build_product_alias_index(products)
    product_lookup_aliases = build_product_lookup_alias_index(source_path, products) if source_path else {}
    manual_mappings, mapping_warnings = load_reviewed_mapping_file(mapping_file, by_id) if mapping_file else ({}, [])
    if rows:
        rows[0]["mapping_file_warnings"] = mapping_warnings

    for row in rows:
        row["candidate_products"] = []
        row["mapping_file_warnings"] = mapping_warnings
        if row["product_id_input"] is not None:
            match = by_id.get(row["product_id_input"])
            if match is not None:
                set_matched(row, match, "local_product_id", 1.0)
                maybe_exclude_non_inventory_service_row(row)
                continue

        orderpro_result = resolve_candidates(by_orderpro_sku.get(row["normalized_orderpro_sku"]), "orderpro_sku")
        if apply_match_result(row, orderpro_result, confidence=1.0):
            maybe_exclude_non_inventory_service_row(row)
            continue

        manual_result = resolve_candidates(manual_mappings.get(manual_mapping_key(row)), "reviewed_mapping_file")
        current_barcode_result = resolve_candidates(by_current_barcode.get(row["barcode"]), "current_product_barcode")
        composite_barcode_result = resolve_alias(alias_index, composite_key("composite_barcode_description", row["normalized_barcode"], row["normalized_name"]))
        composite_code_result = resolve_alias(alias_index, composite_key("composite_code_description", row["normalized_sku"], row["normalized_name"]))
        code_alias_result = resolve_alias(alias_index, alias_key("normalized_code", row["normalized_sku"]))
        barcode_alias_result = resolve_alias(alias_index, alias_key("barcode", row["normalized_barcode"]))
        lookup_result = first_resolved_alias(product_lookup_aliases, lookup_alias_keys(row))

        conflict = first_conflict(
            [
                manual_result,
                current_barcode_result,
                composite_barcode_result,
                composite_code_result,
                code_alias_result,
                barcode_alias_result,
                lookup_result,
            ]
        )
        if conflict is not None:
            mark_ambiguous(
                row,
                "Code and Barcode matched different products.",
                conflict["candidates"],
                status="ambiguous_conflict",
            )
            maybe_exclude_non_inventory_service_row(row)
            continue

        if apply_match_result(row, manual_result, confidence=1.0):
            maybe_exclude_non_inventory_service_row(row)
            continue
        if is_matched_result(current_barcode_result) and apply_match_result(row, current_barcode_result, confidence=0.95):
            maybe_exclude_non_inventory_service_row(row)
            continue
        if apply_match_result(row, composite_barcode_result, confidence=0.93):
            maybe_exclude_non_inventory_service_row(row)
            continue
        if apply_match_result(row, composite_code_result, confidence=0.92):
            maybe_exclude_non_inventory_service_row(row)
            continue
        if apply_match_result(row, code_alias_result, confidence=0.9):
            maybe_exclude_non_inventory_service_row(row)
            continue
        if apply_match_result(row, barcode_alias_result, confidence=0.88):
            maybe_exclude_non_inventory_service_row(row)
            continue
        if apply_match_result(row, lookup_result, confidence=0.88):
            maybe_exclude_non_inventory_service_row(row)
            continue
        if apply_match_result(row, current_barcode_result, confidence=0.86):
            maybe_exclude_non_inventory_service_row(row)
            continue

        name_result = resolve_candidates(by_name.get(row["normalized_name"]), "product_name")
        if apply_match_result(row, name_result, confidence=0.85):
            maybe_exclude_non_inventory_service_row(row)
            continue
        description_result = resolve_candidates(by_description.get(row["normalized_name"]), "product_description")
        if apply_match_result(row, description_result, confidence=0.84):
            maybe_exclude_non_inventory_service_row(row)
            continue
        legacy_result = resolve_candidates(by_legacy_name.get(row["normalized_name"]), "legacy_product_name")
        if apply_match_result(row, legacy_result, confidence=0.8):
            maybe_exclude_non_inventory_service_row(row)
            continue

        row.update({"match_status": "unmatched", "reason": "No deterministic product match."})
        maybe_exclude_non_inventory_service_row(row)
    return rows


def candidate_map(products: list[Product], key_func) -> dict[str, list[Product]]:
    buckets: dict[str, list[Product]] = defaultdict(list)
    for product in products:
        key = key_func(product)
        if key:
            buckets[key].append(product)
    return buckets


def build_product_alias_index(products: list[Product]) -> dict[str, list[Product]]:
    aliases: dict[str, list[Product]] = defaultdict(list)
    for product in products:
        add_alias(aliases, "sku", normalize_token(product.orderpro_sku), product)
        add_alias(aliases, "normalized_code", normalize_token(product.orderpro_sku), product)
        add_alias(aliases, "normalized_code", normalize_token(product.source_key), product)
        add_alias(aliases, "barcode", normalize_token(product.barcode), product)
        add_alias(aliases, "barcode", normalize_barcode(product.barcode), product)
        add_alias(aliases, "name", normalize_name(product.name), product)
        add_alias(aliases, "description", normalize_name(product.description), product)
        add_alias(aliases, "description", normalize_name(product.canonical_description), product)
        for text in [product.name, product.description, product.canonical_description]:
            add_alias(aliases, "composite_barcode_description", composite_value(normalize_token(product.barcode), normalize_name(text)), product)
            add_alias(aliases, "composite_code_description", composite_value(normalize_token(product.source_key), normalize_name(text)), product)
            add_alias(aliases, "composite_code_description", composite_value(normalize_token(product.orderpro_sku), normalize_name(text)), product)
    return aliases


def add_alias(aliases: dict[str, list[Product]], namespace: str, value: str | None, product: Product) -> None:
    if not value:
        return
    key = alias_key(namespace, value)
    if product not in aliases[key]:
        aliases[key].append(product)


def alias_key(namespace: str, value: str | None) -> str | None:
    return f"{namespace}:{value}" if value else None


def composite_value(left: str | None, right: str | None) -> str | None:
    return f"{left}|{right}" if left and right else None


def composite_key(namespace: str, left: str | None, right: str | None) -> str | None:
    return alias_key(namespace, composite_value(left, right))


def resolve_alias(aliases: dict[str, list[Product]], key: str | None) -> dict[str, Any] | None:
    if not key:
        return None
    namespace = key.split(":", 1)[0]
    return resolve_candidates(aliases.get(key), namespace)


def is_matched_result(result: dict[str, Any] | None) -> bool:
    return bool(result and result.get("status") == "matched")


def resolve_candidates(candidates: list[Product] | None, method: str) -> dict[str, Any] | None:
    if not candidates:
        return None
    details = product_candidate_details(candidates)
    if len(candidates) == 1:
        return {"status": "matched", "method": method, "product": candidates[0], "candidates": details}
    return {"status": "ambiguous", "method": method, "candidates": details}


def apply_match_result(row: dict[str, Any], result: dict[str, Any] | None, *, confidence: float) -> bool:
    if result is None:
        return False
    if result["status"] == "ambiguous":
        mark_ambiguous(row, f"Ambiguous {result['method']} match.", result["candidates"])
        return True
    set_matched(row, result["product"], result["method"], confidence)
    return True


def set_matched(row: dict[str, Any], product: Product, method: str, confidence: float) -> None:
    row.update(
        {
            "match_status": "matched",
            "matched_product_id": product.id,
            "matched_product_name": product.name,
            "match_method": method,
            "match_confidence": confidence,
            "reason": f"Matched by {method}.",
            "candidate_products": product_candidate_details([product]),
        }
    )


def mark_ambiguous(row: dict[str, Any], reason: str, candidates: list[dict[str, Any]], *, status: str = "ambiguous") -> None:
    row.update({"match_status": status, "reason": reason, "candidate_products": candidates})


def first_conflict(results: list[dict[str, Any] | None]) -> dict[str, Any] | None:
    matched = [result for result in results if result and result["status"] == "matched"]
    if len({result["product"].id for result in matched}) <= 1:
        return None
    candidates: list[dict[str, Any]] = []
    for result in matched:
        candidates.extend(result["candidates"])
    return {"candidates": candidates}


def product_candidate_details(products: list[Product]) -> list[dict[str, Any]]:
    return [
        {
            "product_id": product.id,
            "orderpro_sku": product.orderpro_sku,
            "source_key": product.source_key,
            "barcode": product.barcode,
            "name": product.name,
            "description": product.description,
            "category": product.category,
            "product_type": product.product_type,
            "source_system": product.source_system,
            "is_non_inventory": product.is_non_inventory,
        }
        for product in products
    ]


def build_product_lookup_alias_index(source_path: Path | None, products: list[Product]) -> dict[str, list[Product]]:
    if source_path is None or source_path.suffix.lower() not in {".xlsx", ".xlsm"}:
        return {}
    try:
        matrices = read_xlsx_sheet_matrices_without_openpyxl(source_path)
    except Exception:
        return {}
    matrix = matrices.get("Product Lookup")
    if not matrix:
        return {}
    header_index, columns, _mapped = detect_lookup_header(matrix)
    if header_index is None:
        return {}
    by_id = {product.id: product for product in products}
    by_sku = candidate_map(products, lambda product: normalize_token(product.orderpro_sku))
    by_barcode = candidate_map(products, lambda product: normalize_barcode(product.barcode))
    by_name = candidate_map(products, lambda product: normalize_name(product.name))
    lookup_aliases: dict[str, list[Product]] = defaultdict(list)
    mapped = {name: find_column(columns, candidates) for name, candidates in PRODUCT_LOOKUP_COLUMN_CANDIDATES.items()}
    for values in matrix[header_index + 1 :]:
        raw = {column: values[index] if index < len(values) else None for index, column in enumerate(columns)}
        if row_is_blank(raw):
            continue
        target = resolve_lookup_target(raw, mapped, by_id=by_id, by_sku=by_sku, by_barcode=by_barcode, by_name=by_name)
        if target is None:
            continue
        old_code = normalize_token(raw.get(mapped["old_code"])) if mapped.get("old_code") else None
        old_barcode = normalize_token(normalize_barcode(raw.get(mapped["old_barcode"]))) if mapped.get("old_barcode") else None
        old_description = normalize_name(raw.get(mapped["old_description"])) if mapped.get("old_description") else None
        add_alias(lookup_aliases, "product_lookup", composite_value(old_code, old_description), target)
        add_alias(lookup_aliases, "product_lookup", composite_value(old_barcode, old_description), target)
        add_alias(lookup_aliases, "product_lookup", old_code, target)
        add_alias(lookup_aliases, "product_lookup", old_barcode, target)
    return lookup_aliases


def detect_lookup_header(matrix: list[list[Any]]) -> tuple[int | None, list[str], dict[str, str | None]]:
    for index, values in enumerate(matrix[:MAX_HEADER_SCAN_ROWS]):
        columns = [clean_header_cell(value) for value in values]
        columns = [column for column in columns if column]
        if not columns:
            continue
        mapped = {name: find_column(columns, candidates) for name, candidates in PRODUCT_LOOKUP_COLUMN_CANDIDATES.items()}
        has_old_identifier = any(mapped.get(key) for key in ["old_code", "old_barcode", "old_description"])
        has_target = any(mapped.get(key) for key in ["product_id", "orderpro_sku", "current_barcode", "current_name"])
        if has_old_identifier and has_target:
            return index, columns, mapped
    return None, [], {name: None for name in PRODUCT_LOOKUP_COLUMN_CANDIDATES}


def resolve_lookup_target(
    raw: dict[str, Any],
    mapped: dict[str, str | None],
    *,
    by_id: dict[int, Product],
    by_sku: dict[str, list[Product]],
    by_barcode: dict[str, list[Product]],
    by_name: dict[str, list[Product]],
) -> Product | None:
    product_id = parse_int(raw.get(mapped["product_id"])) if mapped.get("product_id") else None
    if product_id and product_id in by_id:
        return by_id[product_id]
    candidates: list[Product] = []
    if mapped.get("orderpro_sku"):
        candidates.extend(by_sku.get(normalize_token(raw.get(mapped["orderpro_sku"])), []))
    if mapped.get("current_barcode"):
        candidates.extend(by_barcode.get(normalize_barcode(raw.get(mapped["current_barcode"])), []))
    if mapped.get("current_name"):
        candidates.extend(by_name.get(normalize_name(raw.get(mapped["current_name"])), []))
    unique = {product.id: product for product in candidates}
    return next(iter(unique.values())) if len(unique) == 1 else None


def lookup_alias_keys(row: dict[str, Any]) -> list[str]:
    keys = []
    for value in [
        composite_value(row.get("normalized_sku"), row.get("normalized_name")),
        composite_value(row.get("normalized_barcode"), row.get("normalized_name")),
        row.get("normalized_sku"),
        row.get("normalized_barcode"),
    ]:
        key = alias_key("product_lookup", value)
        if key:
            keys.append(key)
    return keys


def first_resolved_alias(aliases: dict[str, list[Product]], keys: list[str]) -> dict[str, Any] | None:
    for key in keys:
        result = resolve_alias(aliases, key)
        if result:
            return result
    return None


def load_reviewed_mapping_file(mapping_file: str | Path | None, by_id: dict[int, Product]) -> tuple[dict[str, list[Product]], list[str]]:
    if mapping_file is None:
        return {}, []
    path = Path(mapping_file)
    if not path.exists():
        return {}, [f"Mapping file not found: {path}"]
    mappings: dict[str, list[Product]] = {}
    warnings: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, raw in enumerate(reader, start=2):
            product_id = parse_int(raw.get("product_id"))
            product = by_id.get(product_id) if product_id else None
            if product is None:
                warnings.append(f"Mapping row {index} skipped: product_id does not exist.")
                continue
            key = manual_mapping_key(
                {
                    "normalized_sku": normalize_token(raw.get("source_code")),
                    "normalized_barcode": normalize_token(normalize_barcode(raw.get("source_barcode"))),
                    "normalized_name": normalize_name(raw.get("source_description")),
                }
            )
            if key is None:
                warnings.append(f"Mapping row {index} skipped: source identifier is missing.")
                continue
            mappings[key] = [product]
    return mappings, warnings


def manual_mapping_key(row: dict[str, Any]) -> str | None:
    value = "|".join(str(row.get(key) or "") for key in ["normalized_sku", "normalized_barcode", "normalized_name"])
    return alias_key("reviewed_mapping", value) if value.strip("|") else None


def is_non_product_service_row(row: dict[str, Any]) -> bool:
    values = [row.get("product_name"), row.get("sku"), row.get("barcode")]
    normalized_names = {normalize_name(value) for value in values if normalize_name(value)}
    if normalized_names & SERVICE_ROW_TERMS:
        return True
    text = " ".join(str(value or "") for value in values)
    return any(pattern.search(text) for pattern in SERVICE_ROW_PATTERNS)


def has_service_fee_signal(values: list[Any]) -> bool:
    normalized_names = {normalize_name(value) for value in values if normalize_name(value)}
    if normalized_names & SERVICE_ROW_TERMS:
        return True
    text = " ".join(str(value or "") for value in values)
    return any(pattern.search(text) for pattern in SERVICE_ROW_PATTERNS)


def candidate_has_service_fee_signal(candidate: dict[str, Any]) -> bool:
    return has_service_fee_signal(
        [
            candidate.get("name"),
            candidate.get("source_key"),
            candidate.get("orderpro_sku"),
            candidate.get("barcode"),
            candidate.get("description"),
            candidate.get("category"),
            candidate.get("product_type"),
        ]
    )


def candidate_is_clearly_forecastable_inventory(candidate: dict[str, Any]) -> bool:
    is_current_product = bool(candidate.get("source_system") == "orderpro" or candidate.get("orderpro_sku"))
    return bool(is_current_product and not candidate.get("is_non_inventory") and not candidate_has_service_fee_signal(candidate))


def maybe_exclude_non_inventory_service_row(row: dict[str, Any]) -> None:
    candidates = row.get("candidate_products") or []
    row_has_service_signal = is_non_product_service_row(row)
    matched_product_has_service_signal = bool(candidates and candidate_has_service_fee_signal(candidates[0]))
    if not row_has_service_signal and not matched_product_has_service_signal:
        return
    if row.get("match_status") == "matched" and candidates:
        product = candidates[0]
        if candidate_is_clearly_forecastable_inventory(product):
            return
        row["_matched_service_excluded"] = True
    row.update(
        {
            "match_status": "excluded_non_inventory",
            "reason": "Excluded matched service row despite product match."
            if row.get("_matched_service_excluded")
            else "Excluded service/fee row from demand history.",
        }
    )


def validate_demand_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    today = datetime.now(timezone.utc).date()
    for row in rows:
        if row.get("match_status") == "excluded_non_inventory":
            row["duplicate_key"] = demand_row_fingerprint(row)
            row["is_return"] = bool(row["quantity"] is not None and row["quantity"] < 0)
            continue
        invalid_reasons = []
        if row["source_identifier"] is None:
            invalid_reasons.append("missing_product_identifier")
        if is_control_product_name(row.get("product_name")):
            invalid_reasons.append("workbook_control_row")
        if row["date"] is None:
            invalid_reasons.append("invalid_date")
        elif row["date"] > today:
            invalid_reasons.append("future_date")
        if row["quantity"] is None or not math.isfinite(row["quantity"]):
            invalid_reasons.append("invalid_quantity")
        elif row["quantity"] == 0:
            invalid_reasons.append("zero_quantity")

        row["duplicate_key"] = demand_row_fingerprint(row)
        if row["duplicate_key"] in seen:
            row["match_status"] = "duplicate"
            row["reason"] = "Duplicate row within source file."
        else:
            seen.add(row["duplicate_key"])

        if invalid_reasons:
            row["match_status"] = "invalid"
            row["reason"] = "; ".join(invalid_reasons)
        row["is_return"] = bool(row["quantity"] is not None and row["quantity"] < 0)
    return rows


def build_planned_usage_rows(
    db: Session,
    rows: list[dict[str, Any]],
    *,
    source_system: str,
    ignore_existing: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    existing = set() if ignore_existing else {
        (product_id, demand_date)
        for product_id, demand_date in db.query(UsageHistory.product_id, UsageHistory.date)
        .filter(UsageHistory.source_system == source_system)
        .all()
    }
    aggregate = defaultdict(lambda: {"qty_used": 0.0, "qty_returned": 0.0, "net_qty": 0.0, "gross_revenue": 0.0, "source_rows": []})
    already_in_db = 0
    planned_row_count = 0
    for row in rows:
        if row["match_status"] != "matched" or row["date"] is None or row["quantity"] is None:
            continue
        key = (row["matched_product_id"], row["date"])
        if key in existing:
            row["match_status"] = "duplicate"
            row["reason"] = "Usage history already exists for product/date/source."
            already_in_db += 1
            continue
        metrics = aggregate[key]
        quantity = float(row["quantity"])
        if quantity >= 0:
            metrics["qty_used"] += quantity
        else:
            metrics["qty_returned"] += abs(quantity)
        metrics["net_qty"] += quantity
        metrics["gross_revenue"] += float(row["gross_revenue"] or 0)
        metrics["source_rows"].append(row["source_row_number"])
        planned_row_count += 1

    planned = [
        {
            "product_id": product_id,
            "date": demand_date,
            "qty_used": round(values["qty_used"], 4),
            "qty_returned": round(values["qty_returned"], 4),
            "net_qty": round(values["net_qty"], 4),
            "gross_revenue": round(values["gross_revenue"], 4),
        }
        for (product_id, demand_date), values in aggregate.items()
    ]
    return planned, {"rows_already_in_database": already_in_db, "safe_source_rows_aggregated": planned_row_count}


def summarize_plan(
    path: Path,
    rows: list[dict[str, Any]],
    planned_usage_rows: list[dict[str, Any]],
    duplicate_summary: dict[str, int],
    *,
    inspection: dict[str, Any],
) -> dict[str, Any]:
    status_counts = Counter(row["match_status"] for row in rows)
    ambiguous_total = status_counts["ambiguous"] + status_counts["ambiguous_conflict"]
    valid_rows = [row for row in rows if row["match_status"] in {"matched", "duplicate"} and row["date"] is not None]
    quantities = [float(row["quantity"]) for row in rows if row["quantity"] is not None and math.isfinite(float(row["quantity"]))]
    dates = [row["date"] for row in valid_rows if row["date"] is not None]
    warnings = []
    if ambiguous_total:
        warnings.append("Ambiguous product matches were skipped.")
    if status_counts["unmatched"]:
        warnings.append("Unmatched rows require review.")
    if status_counts["excluded_non_inventory"]:
        warnings.append("Non-product service/fee rows were excluded.")
    reinterpreted_date_count = sum(1 for row in rows if row.get("date_reinterpreted_day_first"))
    if reinterpreted_date_count:
        warnings.append(
            f"Reinterpreted {reinterpreted_date_count} ambiguous Excel date cells as day-first "
            "because the same sheet contained strong DD/MM/YYYY text evidence."
        )
    mapping_warnings = next((row.get("mapping_file_warnings") for row in rows if row.get("mapping_file_warnings")), [])
    per_sheet = {}
    for sheet_name in sorted({row["source_sheet"] for row in rows}):
        sheet_rows = [row for row in rows if row["source_sheet"] == sheet_name]
        sheet_status = Counter(row["match_status"] for row in sheet_rows)
        sheet_quantities = [
            float(row["quantity"])
            for row in sheet_rows
            if row["quantity"] is not None and math.isfinite(float(row["quantity"]))
        ]
        per_sheet[sheet_name] = {
            "rows_scanned": inspection.get("sheet_inspection", {}).get(sheet_name, {}).get("rows_scanned", len(sheet_rows)),
            "source_rows": len(sheet_rows),
            "valid_rows": len([row for row in sheet_rows if row["match_status"] in {"matched", "duplicate"}]),
            "matched_rows": sheet_status["matched"],
            "unmatched_rows": sheet_status["unmatched"],
            "ambiguous_rows": sheet_status["ambiguous"] + sheet_status["ambiguous_conflict"],
            "excluded_non_inventory_rows": sheet_status["excluded_non_inventory"],
            "invalid_rows": sheet_status["invalid"],
            "duplicate_rows": sheet_status["duplicate"],
            "dates_reinterpreted_day_first": sum(
                1 for row in sheet_rows if row.get("date_reinterpreted_day_first")
            ),
            "total_positive_quantity": round(sum(qty for qty in sheet_quantities if qty > 0), 4),
            "total_returned_quantity": round(sum(qty for qty in sheet_quantities if qty < 0), 4),
        }
    return {
        "mode": "dry_run",
        "source_file": str(path),
        "total_workbook_rows_scanned": inspection.get("total_workbook_rows_scanned", len(rows)),
        "sheets_included": inspection.get("sheets_included", []),
        "sheets_skipped": inspection.get("sheets_skipped", {}),
        "sheet_inspection": inspection.get("sheet_inspection", {}),
        "total_source_rows": len(rows),
        "valid_sales_rows": len([row for row in rows if row["date"] is not None and row["quantity"] is not None and row["source_identifier"] is not None]),
        "valid_rows": len([row for row in rows if row["match_status"] in {"matched", "duplicate"}]),
        "matched_rows": status_counts["matched"],
        "unmatched_rows": status_counts["unmatched"],
        "ambiguous_rows": ambiguous_total,
        "ambiguous_conflict_rows": status_counts["ambiguous_conflict"],
        "excluded_non_inventory_rows": status_counts["excluded_non_inventory"],
        "matched_service_rows_excluded": sum(1 for row in rows if row.get("_matched_service_excluded")),
        "invalid_rows": status_counts["invalid"],
        "duplicate_rows": status_counts["duplicate"],
        "dates_reinterpreted_day_first": reinterpreted_date_count,
        "rows_already_in_database": duplicate_summary["rows_already_in_database"],
        "rows_planned_for_insert": len(planned_usage_rows),
        "source_rows_planned_for_insert": duplicate_summary["safe_source_rows_aggregated"],
        "affected_products": len({row["product_id"] for row in planned_usage_rows}),
        "earliest_date": min(dates).isoformat() if dates else None,
        "latest_date": max(dates).isoformat() if dates else None,
        "total_positive_quantity": round(sum(qty for qty in quantities if qty > 0), 4),
        "total_returned_quantity": round(sum(qty for qty in quantities if qty < 0), 4),
        "warnings": warnings,
        "mapping_file_warnings": mapping_warnings or [],
        "status_counts": dict(status_counts),
        "per_sheet_counts": per_sheet,
        "top_ambiguity_reasons": top_ambiguity_reasons(rows),
        "grouped_ambiguity_summary": grouped_ambiguity_rows(rows)[:50],
        "ambiguous_samples": [
            ambiguous_sample(row)
            for row in rows
            if row["match_status"] in {"ambiguous", "ambiguous_conflict"}
        ][:25],
    }


def get_demand_reconciliation_summary(db: Session) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    stale_cutoff = today - timedelta(days=180)
    recent_cutoff = today - timedelta(days=90)
    total_products = db.query(func.count(Product.id)).scalar() or 0
    aggregate = (
        db.query(
            func.count(UsageHistory.id).label("total_demand_rows"),
            func.count(func.distinct(UsageHistory.product_id)).label("products_with_demand_history"),
            func.min(UsageHistory.date).label("earliest_demand_date"),
            func.max(UsageHistory.date).label("latest_demand_date"),
        )
        .filter(UsageHistory.source_system == SOURCE_SYSTEM)
        .one()
    )
    product_usage = (
        db.query(
            UsageHistory.product_id.label("product_id"),
            func.max(UsageHistory.date).label("latest_demand_date"),
            func.sum(
                case(
                    (UsageHistory.date >= recent_cutoff, UsageHistory.net_qty),
                    else_=0,
                )
            ).label("units_last_90_days"),
        )
        .filter(UsageHistory.source_system == SOURCE_SYSTEM)
        .group_by(UsageHistory.product_id)
        .subquery()
    )
    recent_products = (
        db.query(func.count())
        .select_from(product_usage)
        .filter(product_usage.c.units_last_90_days > 0)
        .scalar()
        or 0
    )
    stale_products = (
        db.query(func.count())
        .select_from(product_usage)
        .filter(product_usage.c.latest_demand_date < stale_cutoff)
        .scalar()
        or 0
    )
    products_with_history = int(aggregate.products_with_demand_history or 0)
    products_without_history = max(int(total_products) - products_with_history, 0)
    return {
        "total_products": total_products,
        "products_with_demand_history": products_with_history,
        "products_without_demand_history": products_without_history,
        "products_with_recent_demand": recent_products,
        "products_with_stale_demand": stale_products,
        "total_demand_rows": int(aggregate.total_demand_rows or 0),
        "earliest_demand_date": aggregate.earliest_demand_date.isoformat() if aggregate.earliest_demand_date else None,
        "latest_demand_date": aggregate.latest_demand_date.isoformat() if aggregate.latest_demand_date else None,
        "coverage_percentage": round((products_with_history / total_products) * 100, 2) if total_products else 0,
        "products_blocked_by_missing_demand_history": products_without_history,
        "selected_date": today.isoformat(),
    }


def list_demand_coverage_products(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
    has_history: bool | None = None,
    has_recent_demand: bool | None = None,
    stale_only: bool | None = None,
    supplier_id: int | None = None,
    sort_by: str = "latest_demand_date",
    sort_direction: str = "desc",
) -> dict[str, Any]:
    rows = demand_coverage_rows(db, search=search, supplier_id=supplier_id, include_readiness=False)
    if has_history is not None:
        rows = [row for row in rows if row["has_demand_history"] is has_history]
    if has_recent_demand is not None:
        rows = [row for row in rows if (row["units_last_90_days"] > 0) is has_recent_demand]
    if stale_only:
        rows = [row for row in rows if row["stale_demand"]]
    rows = sort_coverage_rows(rows, sort_by, sort_direction)
    page = max(page, 1)
    page_size = min(max(page_size, 1), 250)
    total = len(rows)
    total_pages = (total + page_size - 1) // page_size if total else 0
    start = (page - 1) * page_size
    page_rows = _attach_demand_readiness(db, rows[start : start + page_size])
    return {"items": page_rows, "page": page, "page_size": page_size, "total": total, "total_pages": total_pages}


def get_demand_coverage_detail(db: Session, product_id: int) -> dict[str, Any] | None:
    row = next((item for item in demand_coverage_rows(db, product_id=product_id) if item["product_id"] == product_id), None)
    if row is None:
        return None
    usage_rows = db.query(UsageHistory).filter(UsageHistory.product_id == product_id).all()
    monthly_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"net_units": 0.0, "return_units": 0.0})
    for usage in usage_rows:
        bucket = f"{usage.date.year:04d}-{usage.date.month:02d}"
        monthly_totals[bucket]["net_units"] += float(usage.net_qty or 0)
        monthly_totals[bucket]["return_units"] += float(usage.qty_returned or 0)
    row["monthly_buckets"] = [
        {
            "month": bucket,
            "net_units": round(values["net_units"], 4),
            "return_units": round(values["return_units"], 4),
        }
        for bucket, values in sorted(monthly_totals.items(), reverse=True)[:36]
    ]
    row["source_systems"] = [
        source
        for (source,) in db.query(UsageHistory.source_system)
        .filter(UsageHistory.product_id == product_id)
        .distinct()
        .all()
    ]
    row["readiness_impact"] = "Demand history is present." if row["has_demand_history"] else "Demand history is missing and may keep readiness monitor-only."
    row["current_forecast_demand_source"] = row["demand_source"]
    return row


def _apply_demand_product_search(query, search: str | None):
    normalized = normalize_search_query(search)
    if not normalized:
        return query

    exact_product_id = parse_exact_product_id(normalized)
    if exact_product_id is not None:
        exact_id_exists = query.filter(Product.id == exact_product_id).first()
        if exact_id_exists:
            return query.filter(Product.id == exact_product_id)

    query = query.outerjoin(Supplier, Product.supplier_id == Supplier.id)
    exact_query = query.filter(
        or_(
            func.lower(Product.orderpro_sku) == normalized,
            func.lower(Product.barcode) == normalized,
            func.lower(Product.supplier_sku) == normalized,
        )
    )
    if exact_query.first():
        return exact_query

    like_pattern = f"%{normalized}%"
    return query.filter(
        or_(
            func.lower(Product.name).like(like_pattern),
            func.lower(Product.description).like(like_pattern),
            func.lower(Supplier.name).like(like_pattern),
            func.lower(Supplier.orderpro_code).like(like_pattern),
        )
    )


def demand_coverage_rows(
    db: Session,
    *,
    product_id: int | None = None,
    search: str | None = None,
    supplier_id: int | None = None,
    include_readiness: bool = True,
) -> list[dict[str, Any]]:
    query = (
        db.query(Product)
        .options(selectinload(Product.supplier_record))
        .filter((Product.source_system == "orderpro") | (Product.orderpro_id.is_not(None)) | (Product.orderpro_sku.is_not(None)))
    )
    if product_id is not None:
        query = query.filter(Product.id == product_id)
    if supplier_id is not None:
        query = query.filter(Product.supplier_id == supplier_id)
    query = _apply_demand_product_search(query, search)
    products = query.all()
    product_ids = [product.id for product in products]
    usage_by_product: dict[int, list[UsageHistory]] = defaultdict(list)
    if product_ids:
        for row in db.query(UsageHistory).filter(UsageHistory.product_id.in_(product_ids)).all():
            usage_by_product[row.product_id].append(row)

    today = datetime.now(timezone.utc).date()
    rows = []
    for product in products:
        usage = usage_by_product.get(product.id, [])
        demand_dates = [row.date for row in usage]
        total_units = round(sum(float(row.net_qty or 0) for row in usage), 4)
        return_units = round(sum(float(row.qty_returned or 0) for row in usage), 4)
        last_30 = round(sum(float(row.net_qty or 0) for row in usage if row.date >= today - timedelta(days=30)), 4)
        last_90 = round(sum(float(row.net_qty or 0) for row in usage if row.date >= today - timedelta(days=90)), 4)
        month_keys = {(row.date.year, row.date.month) for row in usage}
        earliest = min(demand_dates).isoformat() if demand_dates else None
        latest_date = max(demand_dates) if demand_dates else None
        months_covered = len(month_keys)
        gap_warnings = coverage_gap_warnings(month_keys, latest_date)
        row = {
                "product_id": product.id,
                "sku": product.orderpro_sku or product.source_key,
                "orderpro_sku": product.orderpro_sku,
                "supplier_sku": product.supplier_sku,
                "barcode": product.barcode,
                "description": product.description,
                "product_name": product.name,
                "supplier_id": product.supplier_id,
                "supplier_code": product.supplier_record.orderpro_code if product.supplier_record else None,
                "supplier_name": product.supplier_record.name if product.supplier_record else None,
                "current_stock": product.current_stock,
                "has_demand_history": bool(usage),
                "demand_row_count": len(usage),
                "earliest_demand_date": earliest,
                "latest_demand_date": latest_date.isoformat() if latest_date else None,
                "months_covered": months_covered,
                "total_units": total_units,
                "units_last_30_days": last_30,
                "units_last_90_days": last_90,
                "average_monthly_units": round(total_units / months_covered, 4) if months_covered else 0,
                "return_units": return_units,
                "stale_demand": bool(latest_date and latest_date < today - timedelta(days=180)),
                "gap_warnings": gap_warnings,
            }
        if include_readiness:
            readiness = evaluate_product_readiness(db, product)
            row.update(
                {
                    "readiness_status": readiness["readiness_status"],
                    "readiness_score": readiness["readiness_score"],
                    "readiness_missing_inputs": readiness["missing_inputs"],
                    "demand_source": readiness["demand_source"],
                }
            )
        else:
            row.update(
                {
                    "readiness_status": "partially_ready" if usage else "monitor_only",
                    "readiness_score": None,
                    "readiness_missing_inputs": [] if usage else ["demand_history"],
                    "demand_source": "usage_history" if usage else "none",
                }
            )
        rows.append(row)
    return rows


def _attach_demand_readiness(db: Session, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return rows
    products = {
        product.id: product
        for product in db.query(Product)
        .options(
            selectinload(Product.supplier_record),
            selectinload(Product.product_suppliers),
            selectinload(Product.forecast_input_profile),
            selectinload(Product.orderpro_order_items),
        )
        .filter(Product.id.in_([row["product_id"] for row in rows]))
        .all()
    }
    enriched = []
    for row in rows:
        product = products.get(row["product_id"])
        if product is None:
            enriched.append(row)
            continue
        readiness = evaluate_product_readiness(db, product)
        updated = dict(row)
        updated.update(
            {
                "readiness_status": readiness["readiness_status"],
                "readiness_score": readiness["readiness_score"],
                "readiness_missing_inputs": readiness["missing_inputs"],
                "demand_source": readiness["demand_source"],
            }
        )
        enriched.append(updated)
    return enriched


def coverage_gap_warnings(month_keys: set[tuple[int, int]], latest_date: date | None) -> list[str]:
    warnings = []
    if not month_keys:
        warnings.append("missing_demand_history")
        return warnings
    if len(month_keys) < 3:
        warnings.append("sparse_demand_history")
    if latest_date and latest_date < datetime.now(timezone.utc).date() - timedelta(days=180):
        warnings.append("stale_demand_history")
    return warnings


def sort_coverage_rows(rows: list[dict[str, Any]], sort_by: str, sort_direction: str) -> list[dict[str, Any]]:
    reverse = sort_direction != "asc"
    key_map = {
        "sku": lambda row: row["sku"] or "",
        "product_name": lambda row: row["product_name"] or "",
        "demand_row_count": lambda row: row["demand_row_count"],
        "latest_demand_date": lambda row: row["latest_demand_date"] or "",
        "months_covered": lambda row: row["months_covered"],
        "units_last_90_days": lambda row: row["units_last_90_days"],
    }
    return sorted(rows, key=key_map.get(sort_by, key_map["latest_demand_date"]), reverse=reverse)


def build_demand_coverage_csv(db: Session, **filters: Any) -> CsvExport:
    result = list_demand_coverage_products(db, page=1, page_size=100000, **filters)
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=DEMAND_COVERAGE_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    for row in result["items"]:
        writer.writerow(
            {
                "product_id": row["product_id"],
                "sku": csv_safe(row["sku"]),
                "product_name": csv_safe(row["product_name"]),
                "supplier_id": row["supplier_id"],
                "supplier_code": csv_safe(row["supplier_code"]),
                "supplier_name": csv_safe(row["supplier_name"]),
                "has_demand_history": row["has_demand_history"],
                "demand_row_count": row["demand_row_count"],
                "earliest_demand_date": row["earliest_demand_date"],
                "latest_demand_date": row["latest_demand_date"],
                "months_covered": row["months_covered"],
                "total_units": row["total_units"],
                "units_last_30_days": row["units_last_30_days"],
                "units_last_90_days": row["units_last_90_days"],
                "average_monthly_units": row["average_monthly_units"],
                "return_units": row["return_units"],
                "stale_demand": row["stale_demand"],
                "gap_warnings": "; ".join(row["gap_warnings"]),
                "readiness_status": row["readiness_status"],
                "readiness_score": row["readiness_score"],
                "demand_source": row["demand_source"],
            }
        )
    filename = f"demand_coverage_{datetime.now(timezone.utc).date().isoformat()}.csv"
    return CsvExport(content=("\ufeff" + handle.getvalue()).encode("utf-8"), filename=filename)


def parse_date(
    value: Any,
    *,
    reinterpret_ambiguous_datetime_day_first: bool = False,
) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, (datetime, date)):
        parsed_date = value.date() if isinstance(value, datetime) else value
        if reinterpret_ambiguous_datetime_day_first and is_ambiguous_datetime_value(parsed_date):
            return date(parsed_date.year, parsed_date.day, parsed_date.month)
        return parsed_date
    numeric_value = parse_float(value)
    if numeric_value is not None and numeric_value > 20000:
        return date(1899, 12, 30) + timedelta(days=int(numeric_value))
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        parsed = pd.to_datetime(value, errors="coerce")
        return None if pd.isna(parsed) else parsed.date()
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def is_ambiguous_datetime_value(value: Any) -> bool:
    if not isinstance(value, (datetime, date)):
        return False
    parsed_date = value.date() if isinstance(value, datetime) else value
    return parsed_date.month <= 12 and parsed_date.day <= 12 and parsed_date.month != parsed_date.day


def infer_day_first_excel_datetime_sheets(
    source_rows: list[dict[str, Any]],
    date_column: str | None,
) -> set[str]:
    if not date_column:
        return set()
    strong_day_first_strings: Counter[str] = Counter()
    ambiguous_datetime_values: Counter[str] = Counter()
    for item in source_rows:
        value = item["raw"].get(date_column)
        sheet = item["source_sheet"]
        if is_ambiguous_datetime_value(value):
            ambiguous_datetime_values[sheet] += 1
            continue
        if not isinstance(value, str):
            continue
        match = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*", value)
        if match and int(match.group(1)) > 12 and int(match.group(2)) <= 12:
            strong_day_first_strings[sheet] += 1
    return {
        sheet
        for sheet, ambiguous_count in ambiguous_datetime_values.items()
        if ambiguous_count > 0 and strong_day_first_strings[sheet] >= 3
    }


def parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def parse_int(value: Any) -> int | None:
    parsed = parse_float(value)
    return int(parsed) if parsed is not None and parsed.is_integer() else None


def is_control_product_name(value: Any) -> bool:
    text = clean_text(value)
    return bool(text and text.upper() in CONTROL_PRODUCT_NAMES)


def ambiguous_sample(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_sheet": row.get("source_sheet"),
        "source_row_number": row.get("source_row_number"),
        "source_code": row.get("sku"),
        "source_barcode": row.get("barcode"),
        "source_description": row.get("product_name"),
        "reason": row.get("reason"),
        "candidate_product_ids": [candidate.get("product_id") for candidate in row.get("candidate_products", [])],
        "candidate_skus": [candidate.get("orderpro_sku") or candidate.get("source_key") for candidate in row.get("candidate_products", [])],
        "candidate_names": [candidate.get("name") for candidate in row.get("candidate_products", [])],
        "candidates": row.get("candidate_products", []),
    }


def top_ambiguity_reasons(rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    counter = Counter(
        row.get("reason") or "unknown"
        for row in rows
        if row.get("match_status") in {"ambiguous", "ambiguous_conflict"}
    )
    return [{"reason": reason, "row_count": count} for reason, count in counter.most_common(limit)]


def grouped_ambiguity_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for row in rows:
        if row.get("match_status") not in {"ambiguous", "ambiguous_conflict"}:
            continue
        key = ambiguity_group_key(row)
        group = groups.setdefault(
            key,
            {
                "source_code": row.get("sku"),
                "source_barcode": row.get("barcode"),
                "source_description": row.get("product_name"),
                "row_count": 0,
                "total_quantity": 0.0,
                "first_date": None,
                "last_date": None,
                "candidate_count": 0,
                "candidate_product_ids": "",
                "candidate_skus": "",
                "candidate_names": "",
                "reason": row.get("reason"),
                "suggested_review_priority": "low",
                "_candidate_ids": set(),
                "_candidate_skus": set(),
                "_candidate_names": set(),
            },
        )
        group["row_count"] += 1
        if row.get("quantity") is not None:
            group["total_quantity"] += float(row["quantity"])
        if row.get("date"):
            date_text = row["date"].isoformat() if hasattr(row["date"], "isoformat") else str(row["date"])
            group["first_date"] = min(filter(None, [group["first_date"], date_text]), default=date_text)
            group["last_date"] = max(filter(None, [group["last_date"], date_text]), default=date_text)
        for candidate in row.get("candidate_products", []):
            group["_candidate_ids"].add(candidate.get("product_id"))
            group["_candidate_skus"].add(candidate.get("orderpro_sku") or candidate.get("source_key"))
            group["_candidate_names"].add(candidate.get("name"))
    grouped = []
    for group in groups.values():
        total_quantity = round(group["total_quantity"], 4)
        candidate_ids = sorted(value for value in group.pop("_candidate_ids") if value is not None)
        candidate_skus = sorted(str(value) for value in group.pop("_candidate_skus") if value)
        candidate_names = sorted(str(value) for value in group.pop("_candidate_names") if value)
        group["total_quantity"] = total_quantity
        group["candidate_count"] = len(candidate_ids)
        group["candidate_product_ids"] = ";".join(str(value) for value in candidate_ids)
        group["candidate_skus"] = ";".join(candidate_skus)
        group["candidate_names"] = ";".join(candidate_names)
        abs_quantity = abs(total_quantity)
        if group["row_count"] >= 50 or abs_quantity >= 500:
            group["suggested_review_priority"] = "high"
        elif group["row_count"] >= 10 or abs_quantity >= 100:
            group["suggested_review_priority"] = "medium"
        grouped.append(group)
    return sorted(grouped, key=lambda item: (item["suggested_review_priority"] != "high", -item["row_count"], -abs(item["total_quantity"])))


def ambiguity_group_key(row: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (row.get("sku"), row.get("barcode"), row.get("product_name"))


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def normalize_token(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    token = re.sub(r"[^A-Z0-9]+", "", text.upper())
    return token or None


def normalize_barcode(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".")[0]
    return text.upper()


def normalize_name(value: Any) -> str | None:
    text = clean_text(value)
    return text.lower() if text else None


def first_present(*values: Any) -> Any:
    return next((value for value in values if value not in {None, ""}), None)


def demand_row_fingerprint(row: dict[str, Any]) -> str:
    parts = [
        row.get("source_file"),
        row.get("source_sheet"),
        row.get("source_identifier"),
        row.get("date"),
        row.get("quantity"),
        row.get("gross_revenue"),
        row.get("external_ref"),
    ]
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def csv_safe(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text
