from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import SessionLocal
from app.services.forecast_input_reconciliation import (
    CALCULATION_VERSION,
    apply_forecast_input_reconciliation,
    plan_forecast_input_reconciliation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply deterministic forecast input reconciliation for OrderPro products."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Report changes without writing anything. This is the default.")
    mode.add_argument("--apply", action="store_true", help="Create/update product forecast input profiles.")
    parser.add_argument("--product-id", type=int, help="Limit reconciliation to one product ID.")
    parser.add_argument("--supplier-id", type=int, help="Limit reconciliation to products for one supplier ID.")
    parser.add_argument("--calculation-version", default=CALCULATION_VERSION)
    parser.add_argument("--save-report", action="store_true", help="Save a JSON report under tmp/forecast_input_reconciliation_reports/.")
    return parser.parse_args()


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def save_report(payload: dict[str, Any], *, mode: str) -> Path:
    report_dir = PROJECT_ROOT / "tmp" / "forecast_input_reconciliation_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = report_dir / f"forecast_input_reconciliation_{mode}_{timestamp}.json"
    path.write_text(json.dumps(payload, indent=2, default=json_default), encoding="utf-8")
    return path


def print_report(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    audit = payload["audit"]
    print(f"Mode: {payload['mode']}")
    print("")
    print("Forecast input audit")
    for key in (
        "total_orderpro_products",
        "products_with_cost_price",
        "products_missing_cost_price",
        "products_with_supplier_id",
        "products_missing_supplier_id",
        "products_with_lead_time_days_directly",
        "products_inheriting_lead_time_from_supplier",
        "products_missing_usable_lead_time",
        "products_with_recent_po_unit_cost",
        "products_with_po_derived_cost",
        "products_where_cost_sources_disagree",
        "products_using_fallback_moq",
        "products_missing_pack_size",
        "suppliers_missing_lead_time",
    ):
        print(f"- {key}: {audit.get(key)}")
    print("")
    print("Reconciliation plan")
    for key, value in summary.items():
        if isinstance(value, dict):
            print(f"- {key}:")
            for nested_key, nested_value in value.items():
                print(f"  - {nested_key}: {nested_value}")
        else:
            print(f"- {key}: {value}")
    print("")
    if payload["samples"].get("improved"):
        print("Sample improved products")
        for sample in payload["samples"]["improved"][:5]:
            print(
                f"- {sample['product_id']} {sample.get('orderpro_sku')}: "
                f"cost={sample['cost_price']} ({sample['cost_source']}), "
                f"lead_time={sample['lead_time_days']} ({sample['lead_time_source']})"
            )
    if payload["samples"].get("still_blocked"):
        print("")
        print("Sample products still blocked or warned")
        for sample in payload["samples"]["still_blocked"][:5]:
            issues = sample["blocking_issues"] + sample["warning_issues"]
            print(f"- {sample['product_id']} {sample.get('orderpro_sku')}: {', '.join(issues)}")
    if payload.get("warnings"):
        print("")
        print("Warnings")
        for warning in payload["warnings"]:
            print(f"- {warning}")


def main() -> int:
    args = parse_args()
    mode = "apply" if args.apply else "dry_run"
    db = SessionLocal()
    try:
        if args.apply:
            plan = apply_forecast_input_reconciliation(
                db,
                product_id=args.product_id,
                supplier_id=args.supplier_id,
                calculation_version=args.calculation_version,
            )
        else:
            plan = plan_forecast_input_reconciliation(
                db,
                product_id=args.product_id,
                supplier_id=args.supplier_id,
                calculation_version=args.calculation_version,
            )
        payload = asdict(plan)
        print_report(payload)
        if args.save_report:
            path = save_report(payload, mode=mode)
            print("")
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
