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
from app.services.manual_supplier_cleanup import (
    apply_missing_supplier_cleanup_import,
    plan_missing_supplier_cleanup_import,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import reviewed missing-supplier cleanup decisions locally.")
    parser.add_argument("--file", required=True, help="Reviewed cleanup CSV/XLSX file.")
    parser.add_argument("--dry-run", action="store_true", help="Preview local confirmations without writing.")
    parser.add_argument("--apply", action="store_true", help="Apply confirmable reviewed supplier assignments locally.")
    parser.add_argument("--reviewed-by", default="manual_supplier_cleanup")
    parser.add_argument("--save-report", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.apply:
            plan = apply_missing_supplier_cleanup_import(
                db,
                args.file,
                reviewed_by=args.reviewed_by,
                limit=args.limit,
            )
        else:
            plan = plan_missing_supplier_cleanup_import(db, args.file, limit=args.limit)
    finally:
        db.close()

    report = {
        "mode": plan.mode,
        "summary": plan.summary,
        "products_confirmed": plan.products_confirmed,
        "warnings": [
            "This import updates local Product.supplier_id only.",
            "It does not write to OrderPro and does not create suppliers.",
            "Supplier names must match exactly and uniquely.",
        ],
    }
    print(json.dumps(report, indent=2, default=str))

    if args.save_report:
        report_dir = ROOT / "tmp" / "manual_supplier_cleanup_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        mode = "apply" if args.apply else "dry_run"
        report_path = report_dir / f"missing_supplier_cleanup_import_{mode}_{timestamp}.json"
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"Saved report to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
