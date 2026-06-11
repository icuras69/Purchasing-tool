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
    build_missing_supplier_cleanup_export,
    write_missing_supplier_cleanup_export,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export missing-supplier OrderPro products for manual review.")
    parser.add_argument("--output", help="Output CSV/XLSX path. Defaults to tmp/manual_supplier_cleanup_exports.")
    parser.add_argument("--format", choices=["csv", "xlsx"], default="csv")
    parser.add_argument("--only-priority", action="store_true")
    parser.add_argument("--include-no-evidence", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-suggested", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--status")
    parser.add_argument("--save-report", action="store_true")
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output = args.output
    if output is None:
        output_dir = ROOT / "tmp" / "manual_supplier_cleanup_exports"
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = "priority" if args.only_priority else "all"
        output = str(output_dir / f"missing_supplier_cleanup_{suffix}_{timestamp}.{args.format}")

    db = SessionLocal()
    try:
        export = build_missing_supplier_cleanup_export(
            db,
            only_priority=args.only_priority,
            include_no_evidence=args.include_no_evidence,
            include_suggested=args.include_suggested,
            status=args.status,
        )
        write_missing_supplier_cleanup_export(export, output, file_format=args.format)
    finally:
        db.close()

    report = {
        "mode": export.mode,
        "summary": export.summary,
        "warnings": [
            "This export is for manual local review only.",
            "It does not assign suppliers or write to OrderPro.",
        ],
    }
    print(json.dumps(report, indent=2, default=str))

    if args.save_report:
        report_dir = ROOT / "tmp" / "manual_supplier_cleanup_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"missing_supplier_cleanup_export_{timestamp}.json"
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"Saved report to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
