from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings  # noqa: E402
from app.services.orderpro_client import (  # noqa: E402
    OrderProClient,
    OrderProClientError,
    OrderProHTTPError,
    extract_records,
    next_page_number,
)


DEFAULT_ENDPOINTS = [
    "/products",
    "/inventory",
    "/suppliers",
    "/purchase-orders",
    "/warehouses",
    "/orders",
]

WAREHOUSE_ALTERNATIVE_ENDPOINTS = [
    "/warehouse",
    "/locations",
    "/inventory/warehouses",
    "/warehouse-locations",
    "/lots",
]

STOCK_COUNT_ENDPOINTS = [
    "https://wms.orderpro.cloud/stock-count",
    "/stock-count",
    "/api/v2/stock-count",
    "/stock-counts",
]

MAX_TEXT_PREVIEW_CHARS = 300


def response_style(payload: Any) -> str:
    if isinstance(payload, list):
        return "plain_list"
    if not isinstance(payload, dict):
        return "scalar"

    data = payload.get("data")
    if isinstance(data, list):
        return "laravel_collection"
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return "nested_paginator"
    if "data" in payload:
        return "data_object"
    return "single_object"


def summarize_json_shape(payload: Any) -> dict[str, Any]:
    records = extract_records(payload)
    first_record = records[0] if records else None
    style = response_style(payload)

    if isinstance(payload, dict):
        top_level_type = "object"
        top_level_keys = sorted(str(key) for key in payload.keys())
    elif isinstance(payload, list):
        top_level_type = "array"
        top_level_keys = []
    else:
        top_level_type = type(payload).__name__
        top_level_keys = []

    if isinstance(first_record, dict):
        first_record_keys = sorted(str(key) for key in first_record.keys())
    else:
        first_record_keys = []

    nested_object_keys = []
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        nested_object_keys = sorted(str(key) for key in payload["data"].keys())

    return {
        "top_level_type": top_level_type,
        "top_level_keys": top_level_keys,
        "response_style": style,
        "record_count_in_payload": len(records),
        "first_record_type": type(first_record).__name__ if first_record is not None else None,
        "first_record_keys": first_record_keys,
        "nested_object_keys": nested_object_keys,
        "pagination": pagination_clues(payload),
        "warnings": warnings_for_payload(payload, style),
    }


def pagination_clues(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "detected": False,
            "current_page": None,
            "last_page": None,
            "per_page": None,
            "total": None,
            "next_page_url": None,
            "next_page_number": None,
        }

    paginator = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    links = payload.get("links") if isinstance(payload.get("links"), dict) else {}
    clues: dict[str, Any] = {
        "detected": False,
        "current_page": paginator.get("current_page") or meta.get("current_page"),
        "last_page": paginator.get("last_page") or meta.get("last_page"),
        "per_page": paginator.get("per_page") or meta.get("per_page"),
        "total": paginator.get("total") or meta.get("total"),
        "next_page_url": paginator.get("next_page_url") or links.get("next"),
        "next_page_number": next_page_number(payload, current_page=1),
        "meta_keys": sorted(str(key) for key in meta.keys()),
        "links_keys": sorted(str(key) for key in links.keys()),
    }

    if clues["current_page"] is not None or clues["last_page"] is not None:
        clues["detected"] = True
    if clues["next_page_url"]:
        clues["detected"] = True
    if clues["meta_keys"] or clues["links_keys"]:
        clues["detected"] = True

    return clues


def warnings_for_payload(payload: Any, style: str) -> list[str]:
    warnings = []
    if style == "nested_paginator":
        warnings.append("Nested paginator detected under top-level data.")
    if isinstance(payload, dict) and payload.get("data") == []:
        warnings.append("No records found on first page.")
    return warnings


def sanitized_sample(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {key: sanitized_sample(value) for key, value in payload.items() if "token" not in str(key).lower()}
    if isinstance(payload, list):
        return [sanitized_sample(value) for value in payload[:3]]
    return payload


def sanitized_text_preview(text: str | None, max_chars: int = MAX_TEXT_PREVIEW_CHARS) -> str:
    if not text:
        return ""
    cleaned = " ".join(text.replace("\x00", " ").split())
    return cleaned[:max_chars]


def sample_filename(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme and parsed.netloc:
        cleaned = f"{parsed.netloc}{parsed.path}".strip("/")
    else:
        cleaned = endpoint.strip("/")
    cleaned = cleaned.replace("/", "_").replace(":", "_") or "root"
    return f"{cleaned}.json"


def discover_endpoint(
    client: OrderProClient,
    endpoint: str,
    output_dir: Path | None = None,
    *,
    fetch_page_2: bool = False,
    save_raw: bool = False,
) -> dict[str, Any]:
    try:
        page = client.generic_get_raw(endpoint)
        result = {
            "endpoint": endpoint,
            "ok": True,
            "status_code": page.status_code,
            "content_type": page.content_type,
            "is_json": page.is_json,
        }
        if page.is_json:
            summary = summarize_json_shape(page.payload)
            result.update(summary)
        else:
            summary = non_json_summary(page.text)
            result.update(summary)
        if fetch_page_2 and summary["pagination"].get("next_page_number"):
            page_2 = client.generic_get_raw(endpoint, params={"page": 2})
            result["page_2"] = {
                "status_code": page_2.status_code,
                "content_type": page_2.content_type,
                "is_json": page_2.is_json,
                **(summarize_json_shape(page_2.payload) if page_2.is_json else non_json_summary(page_2.text)),
            }
        if output_dir:
            saved_paths = save_sample_files(
                endpoint,
                page.payload if page.is_json else page.text,
                summary,
                output_dir=output_dir,
                save_raw=save_raw,
            )
            result["sample_saved_to"] = saved_paths
        return result
    except OrderProHTTPError as error:
        return {
            "endpoint": endpoint,
            "ok": False,
            "status_code": error.status_code,
            "content_type": error.content_type,
            "is_json": None,
            "error": error.message,
        }
    except OrderProClientError as error:
        return {
            "endpoint": endpoint,
            "ok": False,
            "status_code": None,
            "content_type": None,
            "is_json": None,
            "error": str(error),
        }


def non_json_summary(text: str | None) -> dict[str, Any]:
    return {
        "top_level_type": "text",
        "top_level_keys": [],
        "response_style": "non_json",
        "record_count_in_payload": 0,
        "first_record_type": None,
        "first_record_keys": [],
        "nested_object_keys": [],
        "pagination": {
            "detected": False,
            "current_page": None,
            "last_page": None,
            "per_page": None,
            "total": None,
            "next_page_url": None,
            "next_page_number": None,
        },
        "warnings": ["Non-JSON response."],
        "text_preview": sanitized_text_preview(text),
    }


def save_sample_files(
    endpoint: str,
    payload: Any,
    summary: dict[str, Any],
    *,
    output_dir: Path,
    save_raw: bool = False,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = sample_filename(endpoint).removesuffix(".json")
    records = extract_records(payload) if not isinstance(payload, str) else []
    first_record = records[0] if records else (sanitized_text_preview(payload) if isinstance(payload, str) else None)

    summary_path = output_dir / f"{base_name}.summary.json"
    first_record_path = output_dir / f"{base_name}.first-record.json"

    summary_path.write_text(json.dumps(sanitized_sample(summary), indent=2, default=str), encoding="utf-8")
    first_record_path.write_text(
        json.dumps(sanitized_sample(first_record), indent=2, default=str),
        encoding="utf-8",
    )

    saved = {
        "summary": str(summary_path),
        "first_record": str(first_record_path),
    }

    if save_raw:
        raw_path = output_dir / f"{base_name}.raw.json"
        raw_path.write_text(json.dumps(sanitized_sample(payload), indent=2, default=str), encoding="utf-8")
        saved["raw"] = str(raw_path)

    return saved


def print_result(result: dict[str, Any]) -> None:
    print(f"\nEndpoint: {result['endpoint']}")
    print(f"Status: {result.get('status_code')}")
    print(f"Content-Type: {result.get('content_type') or '-'}")
    print(f"JSON: {result.get('is_json')}")
    print(f"OK: {result['ok']}")
    if not result["ok"]:
        print(f"Error: {result.get('error')}")
        return

    print(f"Top-level shape: {result['top_level_type']}")
    print(f"Top-level keys: {', '.join(result['top_level_keys']) or '-'}")
    print(f"Detected response style: {result['response_style']}")
    print(f"Records in first payload: {result['record_count_in_payload']}")
    print(f"First record type: {result['first_record_type']}")
    print(f"First record keys: {', '.join(result['first_record_keys']) or '-'}")
    print(f"Nested object keys: {', '.join(result['nested_object_keys']) or '-'}")
    print(f"Pagination clues: {json.dumps(result['pagination'], default=str)}")
    if result.get("text_preview"):
        print(f"Text preview: {result['text_preview']}")
    if result["warnings"]:
        print(f"Warnings: {'; '.join(result['warnings'])}")
    if result.get("page_2"):
        print(f"Page 2 status: {result['page_2']['status_code']}")
        print(f"Page 2 records: {result['page_2']['record_count_in_payload']}")
    if result.get("sample_saved_to"):
        print(f"Sanitized samples saved to: {json.dumps(result['sample_saved_to'], default=str)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only OrderPro API discovery.")
    parser.add_argument("--run", action="store_true", help="Required to perform read-only GET requests.")
    parser.add_argument(
        "--save-samples",
        action="store_true",
        help="Save sanitized summary and first-record payloads under tmp/orderpro_samples/.",
    )
    parser.add_argument(
        "--save-raw",
        action="store_true",
        help="Also save sanitized full raw payloads. Use only when safe.",
    )
    parser.add_argument(
        "--fetch-page-2",
        action="store_true",
        help="Fetch page 2 when pagination indicates another page is available.",
    )
    parser.add_argument(
        "--include-warehouse-alternatives",
        action="store_true",
        help="Also test alternative warehouse/location read endpoints.",
    )
    parser.add_argument(
        "--include-stock-count",
        action="store_true",
        help="Also test possible stock-count read endpoints and URL.",
    )
    parser.add_argument(
        "--extra-endpoint",
        action="append",
        dest="extra_endpoints",
        help="Additional relative endpoint path to test, such as /stock-count.",
    )
    parser.add_argument(
        "--extra-url",
        action="append",
        dest="extra_urls",
        help="Additional full OrderPro URL to test. Unknown hosts are refused.",
    )
    parser.add_argument(
        "--endpoint",
        action="append",
        dest="endpoints",
        help="Endpoint path to test. Can be supplied multiple times. Defaults to common read endpoints.",
    )
    args = parser.parse_args()

    if not args.run:
        print("Refusing to call OrderPro. Re-run with --run after confirming read-only discovery is intended.")
        return 2

    if not settings.orderpro_sync_enabled:
        print("Refusing to call OrderPro because ORDERPRO_SYNC_ENABLED is not true.")
        return 2

    output_dir = PROJECT_ROOT / "tmp" / "orderpro_samples" if args.save_samples else None
    client = OrderProClient()

    endpoints = args.endpoints or DEFAULT_ENDPOINTS
    if args.include_warehouse_alternatives:
        endpoints = [*endpoints, *WAREHOUSE_ALTERNATIVE_ENDPOINTS]
    if args.include_stock_count:
        endpoints = [*endpoints, *STOCK_COUNT_ENDPOINTS]
    if args.extra_endpoints:
        endpoints = [*endpoints, *args.extra_endpoints]
    if args.extra_urls:
        endpoints = [*endpoints, *args.extra_urls]

    for endpoint in endpoints:
        result = discover_endpoint(
            client,
            endpoint,
            output_dir=output_dir,
            fetch_page_2=args.fetch_page_2,
            save_raw=args.save_raw,
        )
        print_result(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
