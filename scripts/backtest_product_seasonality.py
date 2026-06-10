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

from app.db.session import SessionLocal  # noqa: E402
from app.services.seasonality_backtesting import (  # noqa: E402
    BACKTEST_VERSION,
    apply_backtest_results,
    build_backtest_plan,
)


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)


def _report_from_plan(plan) -> dict[str, Any]:
    return {
        "mode": plan.mode,
        "backtest_version": plan.backtest_version,
        "products_evaluated": plan.products_evaluated,
        "products_skipped": plan.products_skipped,
        "readiness_counts": plan.readiness_counts,
        "aggregate_metrics": plan.aggregate_metrics,
        "largest_improvements": plan.largest_improvements,
        "worst_performers": plan.worst_performers,
        "sample_calculations": plan.results[:10],
        "warnings": plan.warnings,
    }


def _save_report(report: dict[str, Any]) -> Path:
    report_dir = PROJECT_ROOT / "tmp" / "seasonality_backtest_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = report_dir / f"seasonality_backtest_{report['mode']}_{timestamp}.json"
    path.write_text(json.dumps(report, indent=2, default=_json_default), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest advisory product seasonality profiles.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Build a report without writing results. Default.")
    mode.add_argument("--apply", action="store_true", help="Save backtest result records. Does not affect forecasts or POs.")
    parser.add_argument("--product-id", type=int, default=None)
    parser.add_argument("--test-year", type=int, default=None)
    parser.add_argument("--save-report", action="store_true")
    parser.add_argument("--backtest-version", default=BACKTEST_VERSION)
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.apply:
            plan = apply_backtest_results(
                db,
                product_id=args.product_id,
                test_year=args.test_year,
                backtest_version=args.backtest_version,
            )
        else:
            plan = build_backtest_plan(
                db,
                product_id=args.product_id,
                test_year=args.test_year,
                backtest_version=args.backtest_version,
            )
        report = _report_from_plan(plan)

    print("Seasonality backtest report")
    print(f"Mode: {report['mode']}")
    print(f"Products evaluated: {report['products_evaluated']}")
    print(f"Products skipped: {report['products_skipped']}")
    print(f"Readiness counts: {report['readiness_counts']}")
    print(f"Aggregate metrics: {report['aggregate_metrics']}")
    print("No forecast quantities, reorder points, or purchase orders were changed.")

    if args.save_report:
        path = _save_report(report)
        print(f"Saved report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
