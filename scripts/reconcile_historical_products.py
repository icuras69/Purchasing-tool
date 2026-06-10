from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import SessionLocal
from app.services.historical_product_reconciliation import (
    apply_safe_historical_links,
    build_reconciliation_plan,
)
from app.services.seasonality import utc_now


def _json_default(value: Any) -> str:
    if isinstance(value, date | datetime):
        return value.isoformat()
    return str(value)


def build_report(plan, *, mode: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "generated_at": utc_now(),
        "summary": plan.summary,
        "sample_safe_matches": plan.safe_matches[:10],
        "sample_ambiguous_matches": plan.ambiguous_matches[:10],
        "sample_name_suggestions": plan.name_suggestions[:10],
        "warnings": plan.warnings,
    }


def print_report(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"Mode: {report['mode']}")
    print(f"Total OrderPro products: {summary['total_orderpro_products']}")
    print(f"Total historical products: {summary['total_historical_products']}")
    print(f"OrderPro products with valid barcodes: {summary['orderpro_products_with_valid_barcodes']}")
    print(f"Legacy products with valid barcodes: {summary['legacy_products_with_valid_barcodes']}")
    print(f"Unique barcode links: {summary['unique_barcode_matches']}")
    print(f"Safely matched OrderPro products: {summary['safely_matched_orderpro_products']}")
    print(f"Safely matched historical products: {summary['safely_matched_historical_products']}")
    print(f"Duplicate OrderPro barcode groups: {summary['duplicate_orderpro_barcode_groups']}")
    print(f"Duplicate legacy barcode groups: {summary['duplicate_legacy_barcode_groups']}")
    print(f"Unmatched OrderPro products: {summary['unmatched_orderpro_products']}")
    print(f"Unmatched historical products: {summary['unmatched_historical_products']}")
    print(f"Historical usage rows covered: {summary['historical_usage_rows_covered_by_safe_matches']}")
    print(f"Raw historical net quantity covered: {summary['raw_historical_net_quantity_covered_by_safe_matches']}")
    print(f"Links to create: {summary['links_to_create']}")
    print(f"Links to update: {summary['links_to_update']}")
    print(f"Exact-name review suggestions: {summary['exact_name_review_suggestions']}")
    if report["sample_safe_matches"]:
        print("Sample safe matches:")
        for match in report["sample_safe_matches"][:5]:
            print(
                f"  OrderPro {match['orderpro_product_id']} <- historical "
                f"{match['historical_product_id']} ({match['match_method']}={match['match_value']})"
            )
    if report["sample_ambiguous_matches"]:
        print("Sample ambiguous matches:")
        for match in report["sample_ambiguous_matches"][:5]:
            print(f"  {match['reason']} {match['match_value']}")
    if report["warnings"]:
        print("Warnings:")
        for warning in report["warnings"]:
            print(f"  - {warning}")


def save_report(report: dict[str, Any]) -> Path:
    report_dir = PROJECT_ROOT / "tmp" / "historical_product_reconciliation_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
    path = report_dir / f"historical_product_reconciliation_{report['mode']}_{timestamp}.json"
    path.write_text(json.dumps(report, default=_json_default, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile legacy historical products to OrderPro products.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview links without writing. Default.")
    mode.add_argument("--apply", action="store_true", help="Create/update safe historical product links.")
    parser.add_argument("--product-id", type=int, default=None, help="Limit to one OrderPro product id.")
    parser.add_argument("--include-name-suggestions", action="store_true")
    parser.add_argument("--save-report", action="store_true")
    parser.add_argument("--confirm-safe-barcode-matches", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.apply:
            plan = apply_safe_historical_links(
                db,
                product_id=args.product_id,
                include_name_suggestions=args.include_name_suggestions,
                confirm_safe_barcode_matches=args.confirm_safe_barcode_matches,
            )
            report = build_report(plan, mode="apply")
        else:
            plan = build_reconciliation_plan(
                db,
                product_id=args.product_id,
                include_name_suggestions=args.include_name_suggestions,
            )
            report = build_report(plan, mode="dry_run")

        print_report(report)
        if args.save_report:
            path = save_report(report)
            print(f"Saved report: {path}")
        return 0
    except Exception:
        if args.apply:
            db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
