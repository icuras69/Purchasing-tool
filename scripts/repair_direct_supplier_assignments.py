from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal
from app.services.direct_supplier_repair import (
    plan_direct_supplier_repair,
    save_direct_supplier_repair_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Promote safe legacy supplier mappings into products.supplier_id."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Plan repair without writing changes. Default.")
    mode.add_argument("--apply", action="store_true", help="Apply safe promotions locally.")
    parser.add_argument("--product-id", type=int, help="Repair one product only.")
    parser.add_argument("--save-report", action="store_true", help="Save JSON and CSV reports under tmp/.")
    return parser


def print_summary(plan) -> None:
    print("\nDirect supplier repair")
    print("----------------------")
    for key, value in plan.summary().items():
        print(f"{key}: {value}")
    if plan.items:
        print("\nSamples")
        print("-------")
        for item in plan.items[:10]:
            print(
                f"{item.product_id}: {item.status} - {item.reason} "
                f"(supplier={item.promoted_supplier_id}, sku={item.supplier_sku})"
            )


def main() -> None:
    args = build_parser().parse_args()
    db = SessionLocal()
    try:
        plan = plan_direct_supplier_repair(
            db,
            product_id=args.product_id,
            apply=bool(args.apply),
        )
        print_summary(plan)
        if args.save_report:
            paths = save_direct_supplier_repair_report(plan)
            print("\nSaved reports")
            print("-------------")
            for name, path in paths.items():
                print(f"{name}: {path}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
