import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.models  # noqa: F401
from app.db.session import SessionLocal
from app.services.product_supplier_sync import sync_product_suppliers_from_master_items


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill product_suppliers from matched ProductMasterItem rows."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="apply",
        action="store_false",
        help="Preview the backfill without writing anything. This is the default.",
    )
    mode.add_argument(
        "--apply",
        dest="apply",
        action="store_true",
        help="Insert eligible rows into product_suppliers.",
    )
    parser.set_defaults(apply=False)
    return parser.parse_args()


def print_report(report: dict) -> None:
    print()
    print("ProductSupplier Backfill")
    print("========================")
    print(f"Mode: {'APPLY' if report['apply'] else 'DRY RUN'}")
    print(f"Candidate rows with product_id and supplier_id: {report['candidate_rows']}")
    print(f"Created rows: {report['created_rows']}")
    print(f"Updated rows: {report['updated_rows']}")
    print(f"Skipped rows: {report['skipped_rows']}")
    print(f"Conflict rows: {report['conflict_rows']}")

    if report["skipped_samples"]:
        print()
        print("Sample skipped rows:")
        for row in report["skipped_samples"]:
            print(row)

    if report["conflict_samples"]:
        print()
        print("Sample conflict rows:")
        for row in report["conflict_samples"]:
            print(row)

    if report["changed_samples"]:
        print()
        print("Sample rows prepared for create/update:")
        for row in report["changed_samples"]:
            print(row)


def main() -> None:
    args = parse_args()
    db = SessionLocal()

    try:
        summary = sync_product_suppliers_from_master_items(db, dry_run=not args.apply)
        if args.apply:
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
        else:
            db.rollback()

        report = {
            "apply": args.apply,
            "candidate_rows": summary.candidate_count,
            "created_rows": summary.created_count if args.apply else 0,
            "updated_rows": summary.updated_count if args.apply else 0,
            "skipped_rows": summary.skipped_count,
            "conflict_rows": summary.conflict_count,
            "skipped_samples": summary.skipped_samples,
            "conflict_samples": summary.conflict_samples,
            "changed_samples": summary.changed_samples,
        }
        print_report(report)

    finally:
        db.close()


if __name__ == "__main__":
    main()
