from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import SessionLocal
from app.services.seasonality import (
    CALCULATION_VERSION,
    DEFAULT_MINIMUM_HISTORY_MONTHS,
    apply_seasonality_profiles,
    build_seasonality_plan,
    utc_now,
)


def _json_default(value: Any) -> str:
    if isinstance(value, date | datetime):
        return value.isoformat()
    return str(value)


def _profile_sample(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": profile["product_id"],
        "seasonality_tag": profile["seasonality_tag"],
        "confidence_label": profile["confidence_label"],
        "confidence_score": profile["confidence_score"],
        "primary_season": profile["primary_season"],
        "peak_months": profile["peak_months"],
        "history_start": profile["history_start"],
        "history_end": profile["history_end"],
        "years_covered": profile["years_covered"],
        "active_months": profile["active_months"],
    }


def build_report(plan, *, mode: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "generated_at": utc_now(),
        "historical_data_audit": asdict(plan.audit),
        "profiles_to_create": plan.profiles_to_create,
        "profiles_to_update": plan.profiles_to_update,
        "classification_counts": plan.classification_counts,
        "confidence_counts": plan.confidence_counts,
        "insufficient_data_count": plan.insufficient_data_count,
        "sample_profiles": [_profile_sample(profile) for profile in plan.profiles[:10]],
        "warnings": plan.warnings[:50],
    }


def print_report(report: dict[str, Any]) -> None:
    audit = report["historical_data_audit"]
    print(f"Mode: {report['mode']}")
    print(f"Historical source table: {audit['source_table']}")
    print(f"Historical date range: {audit['history_start']} to {audit['history_end']}")
    print(f"Historical rows evaluated: {audit['historical_rows']}")
    print(f"Products matched: {audit['matched_product_count']}")
    print(f"Unmatched raw historical rows: {audit['unmatched_raw_rows']}")
    print(f"Negative/return rows: {audit['negative_quantity_rows']}")
    print(f"Profiles to create: {report['profiles_to_create']}")
    print(f"Profiles to update: {report['profiles_to_update']}")
    print(f"Classification counts: {report['classification_counts']}")
    print(f"Confidence counts: {report['confidence_counts']}")
    print(f"Insufficient-data count: {report['insufficient_data_count']}")
    if report["sample_profiles"]:
        print("Sample profiles:")
        for sample in report["sample_profiles"][:5]:
            print(
                f"  product {sample['product_id']}: {sample['seasonality_tag']} "
                f"({sample['confidence_label']}, peaks={sample['peak_months']})"
            )
    if report["warnings"]:
        print("Warnings:")
        for warning in report["warnings"][:10]:
            print(f"  - {warning}")


def save_report(report: dict[str, Any]) -> Path:
    report_dir = PROJECT_ROOT / "tmp" / "seasonality_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
    path = report_dir / f"seasonality_{report['mode']}_{timestamp}.json"
    path.write_text(json.dumps(report, default=_json_default, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate product seasonality profiles.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview changes without writing. Default.")
    mode.add_argument("--apply", action="store_true", help="Create/update profiles and Product.seasonality_tag.")
    parser.add_argument("--product-id", type=int, default=None)
    parser.add_argument("--minimum-history-months", type=int, default=DEFAULT_MINIMUM_HISTORY_MONTHS)
    parser.add_argument("--calculation-version", default=CALCULATION_VERSION)
    parser.add_argument("--save-report", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.apply:
            plan = apply_seasonality_profiles(
                db,
                product_id=args.product_id,
                minimum_history_months=args.minimum_history_months,
                calculation_version=args.calculation_version,
            )
            report = build_report(plan, mode="apply")
        else:
            plan = build_seasonality_plan(
                db,
                product_id=args.product_id,
                minimum_history_months=args.minimum_history_months,
                calculation_version=args.calculation_version,
            )
            report = build_report(plan, mode="dry_run")

        print_report(report)
        if args.save_report:
            path = save_report(report)
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
