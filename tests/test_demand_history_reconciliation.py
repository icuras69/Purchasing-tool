import csv
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.core.security import settings
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.usage_history import UsageHistory
from app.services.demand_history_reconciliation import (
    apply_demand_import,
    inspect_demand_file,
    plan_demand_import,
    save_ambiguous_review_reports,
    save_demand_report,
)
from app.services.forecast_input_reconciliation import evaluate_product_readiness
from app.services.forecasting import build_forecast


def make_supplier(db_session, name="Demand Supplier"):
    supplier = Supplier(name=name, normalized_name=name.lower(), orderpro_code="DEM", source_system="orderpro", lead_time_days=4)
    db_session.add(supplier)
    db_session.flush()
    return supplier


def make_product(db_session, **overrides):
    suffix = overrides.get("orderpro_sku") or overrides.get("name") or f"DEMAND-{id(overrides)}"
    defaults = {
        "name": "Demand Product",
        "source_system": "orderpro",
        "orderpro_id": f"OP-{suffix}",
        "orderpro_sku": suffix,
        "barcode": None,
        "current_stock": 5,
        "min_order_qty": 1,
        "lead_time_days": 0,
        "safety_stock": 0,
    }
    defaults.update(overrides)
    product = Product(**defaults)
    db_session.add(product)
    db_session.flush()
    return product


def write_csv(path: Path, rows: list[dict]):
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_minimal_xlsx(path: Path, sheets: dict[str, list[list[str]]] | None = None):
    # Tiny enough for tests, and avoids requiring openpyxl in the local venv.
    sheets = sheets or {
        "2025": [
            ["Date", "Quantity", "SKU", "Description", "Gross"],
            ["2026-01-01", "2", "XLSX-SKU", "Xlsx Product", "20"],
        ]
    }

    def cell(value: str) -> str:
        return f'<c t="inlineStr"><is><t>{value}</t></is></c>'

    workbook_sheets = []
    relationships = []
    with zipfile.ZipFile(path, "w") as archive:
        for index, (sheet_name, rows) in enumerate(sheets.items(), start=1):
            workbook_sheets.append(f'<sheet name="{sheet_name}" sheetId="{index}" r:id="rId{index}"/>')
            relationships.append(
                f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
            )
            row_xml = []
            for row in rows:
                row_xml.append("<row>" + "".join(cell(str(value)) for value in row) + "</row>")
            sheet_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                + "".join(row_xml)
                + "</sheetData></worksheet>"
            )
            archive.writestr(f"xl/worksheets/sheet{index}.xml", sheet_xml)
        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(workbook_sheets)
            + "</sheets></workbook>"
        )
        rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(relationships)
            + "</Relationships>"
        )
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", rels_xml)


def base_row(**overrides):
    row = {"Date": "2026-01-02", "Quantity": "3", "SKU": "SKU-1", "Barcode": "", "Description": "Demand Product", "Gross": "30"}
    row.update(overrides)
    return row


def test_csv_and_xlsx_inspection(tmp_path):
    csv_path = tmp_path / "demand.csv"
    write_csv(csv_path, [base_row()])
    xlsx_path = tmp_path / "demand.xlsx"
    write_minimal_xlsx(xlsx_path)

    csv_info = inspect_demand_file(csv_path)
    xlsx_info = inspect_demand_file(xlsx_path)

    assert csv_info["rows"] == 1
    assert csv_info["mapped_columns"]["date"] == "Date"
    assert xlsx_info["extension"] == ".xlsx"
    assert "Date" in xlsx_info["detected_columns"]
    assert xlsx_info["sheets_included"] == ["2025"]


def test_xlsx_default_reads_only_year_sales_sheets_and_reports_skips(tmp_path, db_session):
    make_product(db_session, orderpro_sku="YEAR-SKU")
    path = tmp_path / "workbook.xlsx"
    write_minimal_xlsx(
        path,
        {
            "2024": [["Report title"], ["Date", "Quantity", "Code", "Description", "Gross"], ["2024-01-01", "2", "YEAR-SKU", "Year Product", "10"]],
            "Product Lookup": [["Code", "Description"], ["YEAR-SKU", "10 Foot Blower Hose"]],
            "Customer Lookup": [["Name"], ["SELECT CUSTOMER"]],
            "Suppliers": [["Name"], ["Demand Supplier"]],
        },
    )

    info = inspect_demand_file(path)
    plan = plan_demand_import(db_session, path)

    assert info["sheets_included"] == ["2024"]
    assert info["sheet_inspection"]["2024"]["header_row"] == 2
    assert info["sheets_skipped"]["Product Lookup"] == "not_year_named_sales_sheet"
    assert "10 Foot Blower Hose" not in info["detected_columns"]
    assert plan.summary["total_workbook_rows_scanned"] == 9
    assert plan.summary["sheets_included"] == ["2024"]
    assert plan.summary["sheets_skipped"]["Customer Lookup"] == "not_year_named_sales_sheet"
    assert plan.summary["matched_rows"] == 1


def test_xlsx_sheet_options_and_all_sheets(tmp_path, db_session):
    make_product(db_session, orderpro_sku="YEAR-SKU")
    make_product(db_session, orderpro_sku="CUSTOM-SKU")
    path = tmp_path / "workbook.xlsx"
    write_minimal_xlsx(
        path,
        {
            "2024": [["Date", "Quantity", "Code", "Description"], ["2024-01-01", "2", "YEAR-SKU", "Year Product"]],
            "Reviewed Sales": [["Date", "Quantity", "Code", "Description"], ["2024-02-01", "3", "CUSTOM-SKU", "Custom Product"]],
            "Product Lookup": [["Code", "Description"], ["CUSTOM-SKU", "Lookup Value"]],
        },
    )

    default_plan = plan_demand_import(db_session, path)
    selected_plan = plan_demand_import(db_session, path, sheets=["Reviewed Sales"])
    all_plan = plan_demand_import(db_session, path, all_sheets=True)

    assert default_plan.summary["sheets_included"] == ["2024"]
    assert selected_plan.summary["sheets_included"] == ["Reviewed Sales"]
    assert selected_plan.summary["matched_rows"] == 1
    assert all_plan.summary["sheets_included"] == ["2024", "Reviewed Sales"]
    assert all_plan.summary["matched_rows"] == 2


def test_product_lookup_sheet_is_skipped_as_sales_but_used_as_safe_alias(tmp_path, db_session):
    make_product(db_session, orderpro_sku="CURRENT-SKU", name="Current Product")
    path = tmp_path / "lookup_alias.xlsx"
    write_minimal_xlsx(
        path,
        {
            "2024": [["Date", "Quantity", "Code", "Description"], ["2024-01-01", "2", "OLD-CODE", "Old Product"]],
            "Product Lookup": [
                ["old_code", "old_description", "orderpro_sku"],
                ["OLD-CODE", "Old Product", "CURRENT-SKU"],
            ],
        },
    )

    info = inspect_demand_file(path)
    plan = plan_demand_import(db_session, path)

    assert info["sheets_included"] == ["2024"]
    assert info["sheets_skipped"]["Product Lookup"] == "not_year_named_sales_sheet"
    assert plan.summary["matched_rows"] == 1
    matched = next(row for row in plan.rows if row["match_status"] == "matched")
    assert matched["match_method"] == "product_lookup"


def test_composite_barcode_description_resolves_shared_barcode_variants(tmp_path, db_session):
    make_product(db_session, orderpro_sku="UDDER-250", source_key="UDDERMINT500ML::TENISONUDDERMINT250ML", barcode="UDDERMINT500ML", name="Tenison Udder Mint 250ml")
    make_product(db_session, orderpro_sku="UDDER-500", source_key="UDDERMINT500ML::TENISONUDDERMINT500ML", barcode="UDDERMINT500ML", name="Tenison Udder Mint 500ml")
    path = tmp_path / "demand.csv"
    write_csv(path, [base_row(SKU="", Barcode="UDDERMINT500ML", Description="Tenison Udder Mint 500ml")])

    plan = plan_demand_import(db_session, path)

    assert plan.summary["matched_rows"] == 1
    matched = next(row for row in plan.rows if row["match_status"] == "matched")
    assert matched["match_method"] == "composite_barcode_description"
    assert matched["candidate_products"][0]["name"] == "Tenison Udder Mint 500ml"


def test_shared_barcode_without_matching_description_remains_ambiguous(tmp_path, db_session):
    make_product(db_session, orderpro_sku="UDDER-250", barcode="UDDERMINT500ML", name="Tenison Udder Mint 250ml")
    make_product(db_session, orderpro_sku="UDDER-500", barcode="UDDERMINT500ML", name="Tenison Udder Mint 500ml")
    path = tmp_path / "demand.csv"
    write_csv(path, [base_row(SKU="", Barcode="UDDERMINT500ML", Description="Tenison Udder Mint")])

    plan = plan_demand_import(db_session, path)

    assert plan.summary["ambiguous_rows"] == 1
    row = next(row for row in plan.rows if row["match_status"] == "ambiguous")
    assert row["reason"] == "Ambiguous barcode match."


def test_composite_alias_duplicate_stays_ambiguous(tmp_path, db_session):
    make_product(db_session, orderpro_sku="DUP-1", barcode="DUPBC", name="Duplicate Product")
    make_product(db_session, orderpro_sku="DUP-2", barcode="DUPBC", name="Duplicate Product")
    path = tmp_path / "demand.csv"
    write_csv(path, [base_row(SKU="", Barcode="DUPBC", Description="Duplicate Product")])

    plan = plan_demand_import(db_session, path)

    assert plan.summary["ambiguous_rows"] == 1
    row = next(row for row in plan.rows if row["match_status"] == "ambiguous")
    assert row["reason"] == "Ambiguous composite_barcode_description match."


def test_manual_mapping_file_resolves_previously_ambiguous_row(tmp_path, db_session):
    target = make_product(db_session, orderpro_sku="DUP-1", barcode="DUPBC", name="Duplicate Product A")
    make_product(db_session, orderpro_sku="DUP-2", barcode="DUPBC", name="Duplicate Product B")
    demand_path = tmp_path / "demand.csv"
    write_csv(demand_path, [base_row(SKU="", Barcode="DUPBC", Description="Legacy Duplicate")])
    mapping_path = tmp_path / "mapping.csv"
    write_csv(
        mapping_path,
        [{"source_code": "", "source_barcode": "DUPBC", "source_description": "Legacy Duplicate", "product_id": str(target.id), "reviewed_by": "Maged"}],
    )

    dry_run = plan_demand_import(db_session, demand_path, mapping_file=mapping_path)

    assert dry_run.summary["matched_rows"] == 1
    assert dry_run.rows[0]["match_method"] == "reviewed_mapping_file"
    assert db_session.query(UsageHistory).count() == 0


def test_invalid_mapping_file_rows_are_reported_and_do_not_create_products(tmp_path, db_session):
    make_product(db_session, orderpro_sku="SKU-1")
    demand_path = tmp_path / "demand.csv"
    write_csv(demand_path, [base_row()])
    mapping_path = tmp_path / "bad_mapping.csv"
    write_csv(mapping_path, [{"source_code": "SKU-1", "source_barcode": "", "source_description": "Demand Product", "product_id": "999999"}])

    before = db_session.query(Product).count()
    plan = plan_demand_import(db_session, demand_path, mapping_file=mapping_path)

    assert db_session.query(Product).count() == before
    assert plan.summary["mapping_file_warnings"]


def test_ambiguous_review_and_grouped_summary_are_generated(tmp_path, db_session):
    make_product(db_session, orderpro_sku="AMB-1", barcode="AMB", name="Ambiguous One")
    make_product(db_session, orderpro_sku="AMB-2", barcode="AMB", name="Ambiguous Two")
    path = tmp_path / "demand.csv"
    write_csv(path, [base_row(SKU="", Barcode="AMB", Description="Ambiguous Unknown")])

    plan = plan_demand_import(db_session, path)
    saved = save_ambiguous_review_reports(plan, report_dir=tmp_path)

    review_rows = list(csv.DictReader(Path(saved["ambiguous_review_csv"]).open(encoding="utf-8-sig")))
    grouped_rows = list(csv.DictReader(Path(saved["ambiguous_grouped_csv"]).open(encoding="utf-8-sig")))
    assert review_rows[0]["source_barcode"] == "AMB"
    assert grouped_rows[0]["row_count"] == "1"


def test_service_rows_are_excluded_when_not_current_inventory_products(tmp_path, db_session):
    make_product(db_session, orderpro_sku=None, source_system="legacy", source_key="PACKAGING2::PACKAGING", barcode="PACKAGING2", name="Packaging")
    path = tmp_path / "demand.csv"
    write_csv(path, [base_row(SKU="", Barcode="PACKAGING2", Description="Packaging")])

    plan = plan_demand_import(db_session, path)

    assert plan.summary["excluded_non_inventory_rows"] == 1
    assert plan.summary["rows_planned_for_insert"] == 0


@pytest.mark.parametrize(
    "description",
    ["Fulfillment", "Admin fee", "CUSTOMS 11/10/24", "Shipping"],
)
def test_matched_service_fee_rows_are_excluded(tmp_path, db_session, description):
    make_product(
        db_session,
        orderpro_sku=description.upper().replace(" ", "-"),
        source_key=f"SERVICE::{description.upper()}",
        barcode="SERVICE-CODE",
        name=description,
        source_system="orderpro",
        is_non_inventory=False,
    )
    path = tmp_path / f"{description.replace(' ', '_').replace('/', '_')}.csv"
    write_csv(path, [base_row(SKU="", Barcode="SERVICE-CODE", Description=description)])

    plan = plan_demand_import(db_session, path)

    assert plan.summary["matched_rows"] == 0
    assert plan.summary["excluded_non_inventory_rows"] == 1
    assert plan.summary["matched_service_rows_excluded"] == 1
    assert plan.summary["rows_planned_for_insert"] == 0
    row = plan.rows[0]
    assert row["match_status"] == "excluded_non_inventory"
    assert row["matched_product_id"] is not None
    assert row["reason"] == "Excluded matched service row despite product match."


def test_physical_product_without_service_terms_remains_matched(tmp_path, db_session):
    make_product(db_session, orderpro_sku="HALTER-1", barcode="HALTER-1", name="Training Halter", source_system="orderpro")
    path = tmp_path / "physical.csv"
    write_csv(path, [base_row(SKU="", Barcode="HALTER-1", Description="Training Halter")])

    plan = plan_demand_import(db_session, path)

    assert plan.summary["matched_rows"] == 1
    assert plan.summary["excluded_non_inventory_rows"] == 0
    assert plan.summary["rows_planned_for_insert"] == 1


def test_excluded_service_rows_report_is_generated(tmp_path, db_session):
    make_product(db_session, orderpro_sku="FULFILLMENT", barcode="FULFILLMENT", name="Fulfillment", source_system="orderpro")
    path = tmp_path / "service.csv"
    write_csv(path, [base_row(SKU="", Barcode="FULFILLMENT", Description="Fulfillment")])

    plan = plan_demand_import(db_session, path)
    saved = save_demand_report(plan, report_dir=tmp_path)

    rows = list(csv.DictReader(Path(saved["excluded_service_rows_csv"]).open(encoding="utf-8-sig")))
    assert rows[0]["product_name"] == "Fulfillment"
    assert rows[0]["matched_product_name"] == "Fulfillment"


def test_headerless_year_sheet_uses_standard_sales_columns(tmp_path, db_session):
    make_product(db_session, orderpro_sku="RS1000", source_key="RS1000", barcode="RS1000")
    path = tmp_path / "headerless.xlsx"
    write_minimal_xlsx(
        path,
        {
            "2023": [
                ["Customer A", "RS1000", "1000kg Himalayan Rock Salt", "", "102540", "2023-01-01", "680", "1", "0", "680", "CUST1", "Sales", "", "680", "0"],
                ["Customer B", "RS1000", "1000kg Himalayan Rock Salt", "", "102541", "2023-01-02", "680", "2", "0", "1360", "CUST2", "Sales", "", "1360", "0"],
                ["Customer C", "RS1000", "1000kg Himalayan Rock Salt", "", "102542", "2023-01-03", "680", "3", "0", "2040", "CUST3", "Sales", "", "2040", "0"],
            ]
        },
    )

    info = inspect_demand_file(path)
    plan = plan_demand_import(db_session, path)

    assert info["sheets_included"] == ["2023"]
    assert info["sheet_inspection"]["2023"]["inferred_header"] is True
    assert info["mapped_columns"]["date"] == "Date"
    assert plan.summary["total_positive_quantity"] == 6
    assert plan.summary["matched_rows"] == 3
    assert plan.summary["earliest_date"] == "2023-01-01"


def test_matching_precedence_and_invalid_rows(tmp_path, db_session):
    supplier = make_supplier(db_session)
    direct = make_product(db_session, id=5001, orderpro_sku="DIRECT-SKU", supplier_id=supplier.id)
    sku = make_product(db_session, orderpro_sku="SKU-1", supplier_id=supplier.id)
    barcode = make_product(db_session, orderpro_sku="BC-SKU", barcode="ABC123", supplier_id=supplier.id)
    name = make_product(db_session, orderpro_sku="NAME-SKU", name="Unique Name Product", supplier_id=supplier.id)
    code_conflict = make_product(db_session, orderpro_sku="CODE-CONFLICT", source_key="CONFLICT-CODE", supplier_id=supplier.id)
    barcode_conflict = make_product(db_session, orderpro_sku="BARCODE-CONFLICT", barcode="CONFLICT-BARCODE", supplier_id=supplier.id)
    make_product(db_session, orderpro_sku="AMB-1", name="Ambiguous Name", supplier_id=supplier.id)
    make_product(db_session, orderpro_sku="AMB-2", name="Ambiguous Name", supplier_id=supplier.id)
    path = tmp_path / "demand.csv"
    write_csv(
        path,
        [
            base_row(product_id=str(direct.id), SKU="NOPE"),
            base_row(SKU=sku.orderpro_sku),
            base_row(SKU="", Barcode="ABC123"),
            base_row(SKU="", Barcode="", Description=name.name),
            base_row(SKU="", Barcode="", Description="Ambiguous Name"),
            base_row(SKU=code_conflict.source_key, Barcode=barcode_conflict.barcode),
            base_row(Date="not-a-date"),
            base_row(Quantity="nan"),
            base_row(SKU="", Barcode="", Description="SELECT PRODUCT"),
            base_row(Quantity="-2", SKU=sku.orderpro_sku),
        ],
    )

    plan = plan_demand_import(db_session, path)
    methods = [row["match_method"] for row in plan.rows if row["match_status"] == "matched"]

    assert "local_product_id" in methods
    assert {"orderpro_sku", "normalized_code", "composite_code_description"} & set(methods)
    assert "current_product_barcode" in methods or "normalized_barcode" in methods
    assert "product_name" in methods
    assert plan.summary["ambiguous_rows"] == 2
    assert plan.summary["invalid_rows"] == 3
    assert plan.summary["total_returned_quantity"] == -2
    conflict_row = next(row for row in plan.rows if row["reason"] == "Code and Barcode matched different products.")
    assert {candidate["product_id"] for candidate in conflict_row["candidate_products"]} == {code_conflict.id, barcode_conflict.id}
    assert plan.summary["ambiguous_samples"][0]["candidate_product_ids"]


def test_duplicate_detection_dry_run_apply_and_idempotency(tmp_path, db_session):
    supplier = make_supplier(db_session)
    product = make_product(db_session, orderpro_sku="SKU-1", supplier_id=supplier.id)
    path = tmp_path / "demand.csv"
    write_csv(path, [base_row(), base_row()])

    dry_run = plan_demand_import(db_session, path)
    assert db_session.query(UsageHistory).count() == 0
    assert dry_run.summary["duplicate_rows"] == 1
    assert dry_run.summary["rows_planned_for_insert"] == 1

    applied = apply_demand_import(db_session, path, reviewed_by="Maged")
    assert applied.summary["inserted_usage_rows"] == 1
    assert db_session.query(UsageHistory).filter_by(product_id=product.id).count() == 1

    rerun = apply_demand_import(db_session, path, reviewed_by="Maged")
    assert rerun.summary["inserted_usage_rows"] == 0
    assert db_session.query(UsageHistory).filter_by(product_id=product.id).count() == 1


def test_apply_rolls_back_on_failure(tmp_path, db_session, monkeypatch):
    make_product(db_session, orderpro_sku="SKU-1")
    path = tmp_path / "demand.csv"
    write_csv(path, [base_row()])

    original_commit = db_session.commit

    def fail_commit():
        raise RuntimeError("boom")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError):
        apply_demand_import(db_session, path)
    monkeypatch.setattr(db_session, "commit", original_commit)

    assert db_session.query(UsageHistory).count() == 0


def test_coverage_api_export_auth_and_forecast_reuse(client, unauthenticated_client, admin_auth_headers, tmp_path, db_session, monkeypatch):
    supplier = make_supplier(db_session)
    product = make_product(db_session, orderpro_sku="SKU-1", supplier_id=supplier.id, cost_price=5)
    stale = make_product(db_session, orderpro_sku="STALE", supplier_id=supplier.id)
    db_session.add(
        UsageHistory(
            product_id=stale.id,
            date=date(2022, 1, 1),
            qty_used=1,
            qty_returned=0,
            net_qty=1,
            gross_revenue=5,
            source_system="legacy",
        )
    )
    path = tmp_path / "demand.csv"
    write_csv(path, [base_row(Date=datetime.now().date().isoformat(), Quantity="4")])
    apply_demand_import(db_session, path)

    def fail_orderpro(*_args, **_kwargs):
        raise AssertionError("OrderPro must not be called.")

    monkeypatch.setattr("app.services.orderpro_client.OrderProClient.generic_get", fail_orderpro)

    summary = client.get("/api/demand-history-reconciliation/summary")
    rows = client.get("/api/demand-history-reconciliation/products", params={"has_history": True})
    detail = client.get(f"/api/demand-history-reconciliation/products/{product.id}")
    export = client.get("/api/demand-history-reconciliation/export.csv", params={"has_history": True})

    assert summary.status_code == 200
    assert summary.json()["products_with_demand_history"] == 2
    assert rows.status_code == 200
    assert rows.json()["total"] == 2
    assert detail.status_code == 200
    assert detail.json()["demand_row_count"] == 1
    assert detail.json()["monthly_buckets"][0]["net_units"] == 4
    assert export.status_code == 200
    assert export.content.startswith(b"\xef\xbb\xbf")
    assert "demand_row_count" in export.content.decode("utf-8-sig")

    forecast = build_forecast(db_session, product)
    readiness = evaluate_product_readiness(db_session, product)
    assert forecast["demand_source"] == "usage_history"
    assert readiness["demand_history_available"] is True

    monkeypatch.setattr(settings, "auth_enabled", True)
    unauthenticated_client.headers.pop("Authorization", None)
    assert unauthenticated_client.get("/api/demand-history-reconciliation/summary").status_code == 401
    monkeypatch.setattr(settings, "auth_enabled", False)
    assert unauthenticated_client.get("/api/demand-history-reconciliation/summary").status_code == 200
    client.headers.update(admin_auth_headers)
