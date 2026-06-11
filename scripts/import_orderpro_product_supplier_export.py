from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal
from app.services.orderpro_product_supplier_export import (
    apply_orderpro_product_supplier_export,
    plan_orderpro_product_supplier_export,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import a fresh OrderPro product export into local supplier assignment review suggestions."
    )
    parser.add_argument("--file", required=True, help="Path to the OrderPro product export CSV/XLSX file.")
    parser.add_argument("--dry-run", action="store_true", help="Preview matches without writing anything.")
    parser.add_argument("--apply-suggestions", action="store_true", help="Create/update review suggestions only.")
    parser.add_argument(
        "--confirm-exact-code",
        action="store_true",
        help="Confirm exact product + supplier code/id matches locally.",
    )
    parser.add_argument("--save-report", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if args.confirm_exact_code and not args.apply_suggestions:
        args.apply_suggestions = True

    db = SessionLocal()
    try:
        if args.apply_suggestions:
            plan = apply_orderpro_product_supplier_export(
                db,
                args.file,
                apply_suggestions=True,
                confirm_exact_code=args.confirm_exact_code,
                limit=args.limit,
            )
        else:
            plan = plan_orderpro_product_supplier_export(db, args.file, limit=args.limit)
    finally:
        db.close()

    report = {
        "mode": plan.mode,
        "summary": plan.summary,
        "records_created": plan.records_created,
        "records_updated": plan.records_updated,
        "products_confirmed": plan.products_confirmed,
        "warnings": [
            "This workflow is local-only and does not write to OrderPro.",
            "Name-only supplier matches are review suggestions only.",
            "Fuzzy matching is not used.",
        ],
    }
    print(json.dumps(report, indent=2, default=str))

    if args.save_report:
        output_dir = ROOT / "tmp" / "supplier_assignment_reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        mode = "confirm_exact_code" if args.confirm_exact_code else plan.mode
        output_path = output_dir / f"orderpro_product_supplier_export_{mode}_{timestamp}.json"
        output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"Saved report to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
