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
from app.services.supplier_assignment_review import (
    apply_supplier_assignment_suggestions,
    build_supplier_assignment_review_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan local-only supplier assignment reviews for OrderPro products missing supplier_id."
    )
    parser.add_argument("--dry-run", action="store_true", help="Calculate suggestions without writing anything.")
    parser.add_argument("--apply-suggestions", action="store_true", help="Create/update review records only.")
    parser.add_argument(
        "--confirm-high-confidence",
        action="store_true",
        help="Also confirm strict high-confidence suggestions locally. Requires --apply-suggestions.",
    )
    parser.add_argument("--product-id", type=int, default=None)
    parser.add_argument("--supplier-id", type=int, default=None)
    parser.add_argument("--save-report", action="store_true")
    args = parser.parse_args()

    if args.confirm_high_confidence and not args.apply_suggestions:
        parser.error("--confirm-high-confidence requires --apply-suggestions.")

    db = SessionLocal()
    try:
        if args.apply_suggestions:
            plan = apply_supplier_assignment_suggestions(
                db,
                product_id=args.product_id,
                supplier_id=args.supplier_id,
                confirm_high_confidence=args.confirm_high_confidence,
            )
        else:
            plan = build_supplier_assignment_review_report(
                db,
                product_id=args.product_id,
                supplier_id=args.supplier_id,
            )
    finally:
        db.close()

    report = {
        "mode": plan.mode,
        "summary": plan.summary,
        "records_created": plan.records_created,
        "records_updated": plan.records_updated,
        "products_confirmed": plan.products_confirmed,
        "sample_items": plan.items[:20],
        "warnings": [
            "Supplier assignment confirmations are local only and are not pushed to OrderPro.",
            "Unconfirmed suggestions do not drive forecasts or purchase order generation.",
        ],
    }
    print(json.dumps(report, indent=2, default=str))
    if args.save_report:
        output_dir = ROOT / "tmp" / "supplier_assignment_reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"supplier_assignment_{plan.mode}_{timestamp}.json"
        output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"Saved report to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
