from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.orderpro_client import OrderProClient  # noqa: E402
from app.services.orderpro_purchase_order_sync import (  # noqa: E402
    apply_orderpro_purchase_order_sync,
    extract_purchase_order_items,
    fetch_orderpro_purchase_orders,
    normalize_orderpro_purchase_order_status,
    plan_orderpro_purchase_order_sync,
)
from app.services.orderpro_sync_planner import sanitize_snapshot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only OrderPro purchase order mirror sync.")
    parser.add_argument("--run", action="store_true", help="Required to call read-only OrderPro endpoints.")
    parser.add_argument("--dry-run", action="store_true", help="Plan changes without writing. This is the default.")
    parser.add_argument("--apply", action="store_true", help="Apply the mirror sync to local read-only OrderPro PO tables.")
    parser.add_argument("--limit-pages", type=int, default=None, help="Optional /purchase-orders page limit.")
    parser.add_argument("--save-report", action="store_true", help="Save JSON report under tmp/orderpro_purchase_order_reports/.")
    parser.add_argument("--save-samples", action="store_true", help="Save a sanitized first-record sample under ignored tmp/.")
    parser.add_argument("--since", help="Reserved for future APIs that support updated-since filters.")
    args = parser.parse_args()

    if args.since:
        print("--since is not supported by the current OrderPro client yet; run without it.")
        return 2
    if not args.run:
        print("Refusing to call OrderPro. Re-run with --run after confirming read-only PO discovery/sync is intended.")
        return 2
    if not settings.orderpro_sync_enabled:
        print("Refusing to call OrderPro because ORDERPRO_SYNC_ENABLED is not true.")
        return 2

    client = OrderProClient()
    purchase_orders = fetch_orderpro_purchase_orders(client, limit_pages=args.limit_pages)

    db = SessionLocal()
    try:
        if args.apply:
            report = apply_orderpro_purchase_order_sync(db, purchase_orders)
            db.commit()
        else:
            report = plan_orderpro_purchase_order_sync(db, purchase_orders)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print_report(report)
    if args.save_report:
        print(f"\nSaved {report.get('mode', 'dry_run')} report to: {save_report(report)}")
    if args.save_samples and purchase_orders:
        for status, path in save_samples_by_status(purchase_orders).items():
            print(f"Saved sanitized {status} sample to: {path}")
    return 0


def print_report(report: dict[str, Any]) -> None:
    print("\nOrderPro Purchase Order Mirror")
    print(f"Mode: {report.get('mode', 'dry_run')}")
    print_section("Summary", report["summary"])
    if report.get("report_notes"):
        print("\nReport notes")
        for note in report["report_notes"]:
            print(f"- {note}")
    print_section("Quantity field coverage", report["summary"].get("quantity_field_coverage", {}))
    print_section("Open quantity by status", report["summary"].get("open_quantity_by_status", {}))
    print_section("Excluded quantity by status", report["summary"].get("excluded_quantity_by_status", {}))
    print_section("Warning counts by type", report["summary"].get("warning_counts_by_type", {}))
    print_samples("Sample open lines", report.get("sample_open_lines", []))
    print_samples("Sample received lines", report.get("sample_received_lines", []))
    print_samples("Items missing product match", report.get("items_missing_product_match_sample", []))
    print_samples("Headers missing supplier match", report.get("headers_missing_supplier_match_sample", []))
    if report.get("warnings"):
        print("\nWarnings")
        for warning in report["warnings"]:
            print(f"- {warning}")


def print_section(title: str, values: dict[str, Any]) -> None:
    print(f"\n{title}")
    for key, value in values.items():
        print(f"- {key}: {value}")


def print_samples(title: str, values: list[Any]) -> None:
    if not values:
        return
    print(f"\n{title}")
    for value in values[:10]:
        print(f"- {json.dumps(value, default=str)}")


def save_report(report: dict[str, Any]) -> Path:
    output_dir = PROJECT_ROOT / "tmp" / "orderpro_purchase_order_reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"orderpro_purchase_orders_{report.get('mode', 'dry_run')}_{timestamp}.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return path


def save_samples_by_status(rows: list[dict[str, Any]]) -> dict[str, Path]:
    samples: dict[str, Path] = {}
    for row in rows:
        status = normalize_orderpro_purchase_order_status(row.get("status")) or "unknown"
        if status in samples:
            continue
        samples[status] = save_sample(row, status=status)
    return samples


def save_sample(row: dict[str, Any], *, status: str) -> Path:
    output_dir = PROJECT_ROOT / "tmp" / "orderpro_purchase_order_samples"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_status = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in status)
    path = output_dir / f"purchase_order_sample_{safe_status}_{timestamp}.json"
    payload = sanitize_snapshot(row)
    if isinstance(payload, dict):
        payload["_sample_summary"] = {
            "status": status,
            "header_keys": sorted(str(key) for key in row.keys()),
            "line_count": len(extract_purchase_order_items(row)),
            "line_keys": [
                sorted(str(key) for key in item.keys())
                for item in extract_purchase_order_items(row)[:3]
            ],
            "quantity_fields": [
                {
                    "id": item.get("id"),
                    "qty": item.get("qty"),
                    "qty_received": item.get("qty_received"),
                    "unit_cost": item.get("unit_cost"),
                    "total": item.get("total"),
                }
                for item in extract_purchase_order_items(row)[:3]
            ],
        }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
