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
from app.services.orderpro_sync_planner import (  # noqa: E402
    apply_orderpro_supplier_product_sync,
    fetch_orderpro_records,
    fetch_orderpro_records_with_status,
    load_product_csv,
    plan_orderpro_sync,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run OrderPro supplier/product/inventory/order sync planner.")
    parser.add_argument("--run", action="store_true", help="Required to call read-only OrderPro endpoints.")
    parser.add_argument("--products-csv", help="Path to the OrderPro product export CSV.")
    parser.add_argument(
        "--limit-pages",
        type=int,
        default=None,
        help="Fallback page limit for products/inventory, and for suppliers only if --supplier-limit-pages is set.",
    )
    parser.add_argument(
        "--supplier-limit-pages",
        type=int,
        default=None,
        help="Optional supplier page limit. Omit by default so supplier codes are checked against all supplier pages.",
    )
    parser.add_argument(
        "--product-limit-pages",
        type=int,
        default=None,
        help="Optional product page limit. Defaults to --limit-pages when omitted.",
    )
    parser.add_argument(
        "--inventory-limit-pages",
        type=int,
        default=None,
        help="Optional inventory page limit. Defaults to --limit-pages when omitted.",
    )
    parser.add_argument(
        "--purchase-order-limit-pages",
        type=int,
        default=None,
        help="Optional /purchase-orders page limit. Reserved for later purchase-order planning.",
    )
    parser.add_argument(
        "--order-limit-pages",
        type=int,
        default=None,
        help="Optional /orders page limit. Defaults to --limit-pages when omitted.",
    )
    parser.add_argument(
        "--include-inventory",
        action="store_true",
        help="Also fetch /inventory and include warehouse/inventory-position planning.",
    )
    parser.add_argument(
        "--include-orders",
        action="store_true",
        help="Also fetch /orders and include OrderPro demand order planning.",
    )
    parser.add_argument(
        "--save-report",
        action="store_true",
        help="Save the JSON dry-run report under tmp/orderpro_sync_reports/.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply supplier and product sync. Omit for dry-run planning.",
    )
    parser.add_argument(
        "--mark-missing-inactive",
        action="store_true",
        help="When applying, mark local OrderPro products absent from the fetched product set inactive.",
    )
    args = parser.parse_args()

    if not args.run:
        print("Refusing to call OrderPro. Re-run with --run after confirming read-only dry-run planning is intended.")
        return 2

    if not settings.orderpro_sync_enabled:
        print("Refusing to call OrderPro because ORDERPRO_SYNC_ENABLED is not true.")
        return 2

    if not args.products_csv and not args.include_orders:
        print("Product CSV is required unless only OrderPro order planning is requested with --include-orders.")
        return 2

    csv_path = Path(args.products_csv) if args.products_csv else None
    if csv_path is not None and not csv_path.exists():
        print(f"Product CSV not found: {csv_path}")
        return 2

    client = OrderProClient()
    product_csv_rows = load_product_csv(csv_path) if csv_path is not None else {}
    supplier_limit_pages = args.supplier_limit_pages
    product_limit_pages = args.product_limit_pages if args.product_limit_pages is not None else args.limit_pages
    inventory_limit_pages = args.inventory_limit_pages if args.inventory_limit_pages is not None else args.limit_pages
    order_limit_pages = args.order_limit_pages if args.order_limit_pages is not None else args.limit_pages
    should_fetch_products = csv_path is not None or args.include_inventory
    should_fetch_suppliers = csv_path is not None
    supplier_fetch = (
        fetch_orderpro_records_with_status(client, "/suppliers", limit_pages=supplier_limit_pages)
        if should_fetch_suppliers
        else None
    )
    suppliers = supplier_fetch.records if supplier_fetch is not None else []
    products = fetch_orderpro_records(client, "/products", limit_pages=product_limit_pages) if should_fetch_products else []
    inventory = (
        fetch_orderpro_records(client, "/inventory", limit_pages=inventory_limit_pages)
        if args.include_inventory
        else None
    )
    orders = fetch_orderpro_records(client, "/orders", limit_pages=order_limit_pages) if args.include_orders else None

    db = SessionLocal()
    try:
        if args.apply:
            report = apply_orderpro_supplier_product_sync(
                db,
                suppliers=suppliers,
                products=products,
                product_csv_rows=product_csv_rows,
                inventory=inventory if args.include_inventory else None,
                orders=orders if args.include_orders else None,
                mark_missing_inactive=args.mark_missing_inactive,
            )
            db.commit()
        else:
            report = plan_orderpro_sync(
                db,
                suppliers=suppliers,
                products=products,
                product_csv_rows=product_csv_rows,
                inventory=inventory,
                orders=orders,
                supplier_pages_limited=supplier_fetch.truncated_by_limit if supplier_fetch is not None else False,
            )
    finally:
        db.close()

    print_report(report)
    if args.save_report:
        path = save_report(report)
        print(f"\nSaved {report.get('mode', 'dry_run')} report to: {path}")

    return 0


def print_report(report: dict[str, Any]) -> None:
    print("\nOrderPro Sync Plan")
    print(f"Mode: {report.get('mode', 'dry_run')}")
    print_section("Supplier summary", report["suppliers"]["summary"])
    print_section("Product summary", report["products"]["summary"])
    if report.get("mode") != "apply":
        print_section(
            "Supplier assignment summary",
            {
                "would_assign_supplier": report["products"]["summary"]["would_assign_supplier"],
                "would_remain_without_supplier": report["products"]["summary"]["would_remain_without_supplier"],
                "missing_from_csv": report["products"]["summary"]["missing_from_csv"],
                "csv_rows_missing_supplier_code": report["products"]["summary"]["csv_rows_missing_supplier_code"],
                "unknown_supplier_codes": report["products"]["summary"]["unknown_supplier_codes"],
            },
        )
    print_samples("Unknown supplier code samples", report["products"].get("unknown_supplier_code_samples", []))
    print_samples(
        "CSV rows missing supplier_code sample",
        report["products"].get("csv_rows_missing_supplier_code_sample", []),
    )
    print_samples(
        "Products remaining without supplier_id sample",
        report["products"].get("would_remain_without_supplier_sample", []),
    )
    if "inventory" in report:
        print_section("Inventory summary", report["inventory"]["summary"])
        print_samples("Inventory rows missing product sample", report["inventory"].get("rows_missing_product_match_sample", []))
        print_samples("Inventory rows missing warehouse sample", report["inventory"].get("rows_missing_warehouse_id_sample", []))
    if "orders" in report:
        print_section("Order demand summary", report["orders"]["summary"])
        print_samples("Order items missing product sample", report["orders"].get("items_missing_product_match_sample", []))
    if report["warnings"]:
        print("\nWarnings")
        for warning in report["warnings"]:
            print(f"- {warning}")
    if report.get("next_recommended_step"):
        print(f"\nNext recommended step: {report['next_recommended_step']}")


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
    output_dir = PROJECT_ROOT / "tmp" / "orderpro_sync_reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = current_utc_timestamp_for_filename()
    mode = report.get("mode", "dry_run")
    path = output_dir / f"orderpro_sync_{mode}_{timestamp}.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return path


def current_utc_timestamp_for_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


if __name__ == "__main__":
    raise SystemExit(main())
