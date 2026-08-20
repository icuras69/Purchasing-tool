import argparse
from pathlib import Path

from app.db.session import SessionLocal
from app.services.demand_history_reconciliation import (
    apply_demand_import,
    inspect_demand_file,
    plan_demand_import,
    save_ambiguous_review_reports,
    save_demand_report,
)


def print_section(title: str, data: dict):
    print(f"\n{title}")
    print("-" * len(title))
    for key, value in data.items():
        print(safe_console_text(f"{key}: {value}"))


def safe_console_text(value: str) -> str:
    encoding = getattr(__import__("sys").stdout, "encoding", None) or "utf-8"
    return value.encode(encoding, errors="replace").decode(encoding, errors="replace")


def parse_sheet_names(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def main():
    parser = argparse.ArgumentParser(description="Plan or apply a safe local demand history import.")
    parser.add_argument("--file", required=True, help="Path to a CSV or XLSX historical demand file.")
    parser.add_argument("--apply", action="store_true", help="Insert safe matched rows into usage_history.")
    parser.add_argument("--sheets", default=None, help="Comma-separated workbook sheet names to inspect/import.")
    parser.add_argument("--all-sheets", action="store_true", help="Inspect/import all workbook sheets that contain sales headers.")
    parser.add_argument("--reviewed-by", default=None, help="Reviewer name recorded in the report when applying.")
    parser.add_argument("--save-report", action="store_true", help="Save JSON and row-level reconciliation CSV reports under tmp/.")
    parser.add_argument("--save-ambiguous-review", action="store_true", help="Save ambiguous-row review and grouped ambiguity CSV reports under tmp/.")
    parser.add_argument("--mapping-file", default=None, help="Optional reviewed mapping CSV used only for planning/matching.")
    parser.add_argument(
        "--replace-existing-source",
        action="store_true",
        help=(
            "With --apply, replace existing demand_history_import rows for products matched in this file. "
            "Use after reviewing a corrected dry-run, such as the mixed Excel day/month date repair."
        ),
    )
    args = parser.parse_args()

    if args.replace_existing_source and not args.apply:
        parser.error("--replace-existing-source requires --apply.")

    path = Path(args.file)
    sheets = parse_sheet_names(args.sheets)
    db = SessionLocal()
    try:
        inspection = inspect_demand_file(path, sheets=sheets, all_sheets=args.all_sheets)
        print_section("File inspection", inspection)
        if args.apply:
            plan = apply_demand_import(
                db,
                path,
                reviewed_by=args.reviewed_by,
                sheets=sheets,
                all_sheets=args.all_sheets,
                mapping_file=args.mapping_file,
                replace_existing_source=args.replace_existing_source,
            )
        else:
            plan = plan_demand_import(
                db,
                path,
                sheets=sheets,
                all_sheets=args.all_sheets,
                mapping_file=args.mapping_file,
            )
        print_section("Demand import summary", plan.summary)
        if args.save_report:
            print_section("Saved reports", save_demand_report(plan))
        if args.save_ambiguous_review:
            print_section("Saved ambiguous review reports", save_ambiguous_review_reports(plan))
    finally:
        db.close()


if __name__ == "__main__":
    main()
