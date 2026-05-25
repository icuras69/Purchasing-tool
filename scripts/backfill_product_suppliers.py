import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.models  # noqa: F401
from app.db.session import SessionLocal
from app.models.product_master_item import ProductMasterItem
from app.models.product_supplier import ProductSupplier


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
    print(f"Matched ProductMasterItem rows: {report['matched_rows']}")
    print(f"Candidate rows with product_id and supplier_id: {report['candidate_rows']}")
    print(f"Inserted rows: {report['inserted_rows']}")
    print(f"Skipped existing rows: {report['skipped_existing_rows']}")
    print(f"Skipped missing FK rows: {report['skipped_missing_fk_rows']}")
    print(f"Skipped duplicate/conflict rows: {report['skipped_conflict_rows']}")

    if report["missing_fk_samples"]:
        print()
        print("Sample matched rows skipped for missing product_id or supplier_id:")
        for row in report["missing_fk_samples"]:
            print(row)

    if report["conflict_samples"]:
        print()
        print("Sample rows skipped for duplicate/conflict supplier_id + supplier_sku:")
        for row in report["conflict_samples"]:
            print(row)

    if report["insert_samples"]:
        print()
        print("Sample rows prepared for insert:")
        for row in report["insert_samples"]:
            print(row)


def main() -> None:
    args = parse_args()
    db = SessionLocal()

    report = {
        "apply": args.apply,
        "matched_rows": 0,
        "candidate_rows": 0,
        "inserted_rows": 0,
        "skipped_existing_rows": 0,
        "skipped_missing_fk_rows": 0,
        "skipped_conflict_rows": 0,
        "missing_fk_samples": [],
        "conflict_samples": [],
        "insert_samples": [],
    }

    try:
        matched_rows = (
            db.query(ProductMasterItem)
            .filter(ProductMasterItem.match_status == "matched")
            .order_by(ProductMasterItem.id.asc())
            .all()
        )
        report["matched_rows"] = len(matched_rows)

        missing_fk_rows = [
            item
            for item in matched_rows
            if item.product_id is None or item.supplier_id is None
        ]
        report["skipped_missing_fk_rows"] = len(missing_fk_rows)
        report["missing_fk_samples"] = [
            {
                "id": item.id,
                "sku": item.sku,
                "product_id": item.product_id,
                "supplier_id": item.supplier_id,
                "match_status": item.match_status,
                "match_method": item.match_method,
            }
            for item in missing_fk_rows[:10]
        ]

        candidates = [
            item
            for item in matched_rows
            if item.product_id is not None and item.supplier_id is not None
        ]
        report["candidate_rows"] = len(candidates)

        candidate_keys = [
            (item.supplier_id, item.sku)
            for item in candidates
            if item.sku is not None
        ]
        duplicate_keys = {
            key
            for key, count in Counter(candidate_keys).items()
            if count > 1
        }

        existing_keys = set(
            db.query(ProductSupplier.supplier_id, ProductSupplier.supplier_sku)
            .filter(ProductSupplier.supplier_sku.is_not(None))
            .all()
        )

        rows_to_insert = []
        seen_keys = set()
        now = datetime.utcnow()

        for item in candidates:
            key = (item.supplier_id, item.sku)

            if key in existing_keys:
                report["skipped_existing_rows"] += 1
                continue

            if key in duplicate_keys or key in seen_keys:
                report["skipped_conflict_rows"] += 1
                if len(report["conflict_samples"]) < 10:
                    report["conflict_samples"].append(
                        {
                            "id": item.id,
                            "sku": item.sku,
                            "product_id": item.product_id,
                            "supplier_id": item.supplier_id,
                            "reason": "duplicate supplier_id + supplier_sku in candidates",
                        }
                    )
                continue

            seen_keys.add(key)

            rows_to_insert.append(
                ProductSupplier(
                    product_id=item.product_id,
                    supplier_id=item.supplier_id,
                    supplier_sku=item.sku,
                    supplier_product_name=item.name,
                    purchase_price=item.cost_price,
                    is_preferred=False,
                    match_status=item.match_status,
                    match_method=item.match_method,
                    last_synced_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )

            if len(report["insert_samples"]) < 10:
                report["insert_samples"].append(
                    {
                        "product_id": item.product_id,
                        "supplier_id": item.supplier_id,
                        "supplier_sku": item.sku,
                        "supplier_product_name": item.name,
                        "purchase_price": item.cost_price,
                        "match_status": item.match_status,
                        "match_method": item.match_method,
                    }
                )

        if args.apply:
            try:
                db.add_all(rows_to_insert)
                db.commit()
                report["inserted_rows"] = len(rows_to_insert)
            except Exception:
                db.rollback()
                raise
        else:
            db.rollback()
            report["inserted_rows"] = 0

        print_report(report)

    finally:
        db.close()


if __name__ == "__main__":
    main()
