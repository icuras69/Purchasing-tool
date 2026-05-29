import httpx

from app.services.orderpro_client import OrderProClient
from scripts.discover_orderpro_api import (
    discover_endpoint,
    non_json_summary,
    pagination_clues,
    response_style,
    sanitized_sample,
    sanitized_text_preview,
    sample_filename,
    save_sample_files,
    summarize_json_shape,
)


def test_discovery_summarizes_json_shape_without_token_leakage():
    payload = {
        "data": [
            {
                "id": 1,
                "sku": "SKU-1",
                "name": "Product",
                "api_token": "secret-token",
            }
        ],
        "meta": {"current_page": 1, "last_page": 1},
    }

    summary = summarize_json_shape(payload)
    sanitized = sanitized_sample(payload)

    assert summary["top_level_type"] == "object"
    assert summary["response_style"] == "laravel_collection"
    assert summary["record_count_in_payload"] == 1
    assert summary["first_record_keys"] == ["api_token", "id", "name", "sku"]
    assert summary["nested_object_keys"] == []
    assert sanitized["data"][0] == {"id": 1, "sku": "SKU-1", "name": "Product"}
    assert "secret-token" not in str(sanitized)


def test_discovery_extracts_nested_paginator_shape():
    payload = {
        "data": {
            "current_page": 1,
            "data": [{"id": 1, "name": "Nested Supplier"}],
            "last_page": 3,
            "per_page": 25,
            "total": 60,
        },
        "meta": {"request_id": "abc"},
    }

    summary = summarize_json_shape(payload)

    assert response_style(payload) == "nested_paginator"
    assert summary["record_count_in_payload"] == 1
    assert summary["first_record_keys"] == ["id", "name"]
    assert summary["nested_object_keys"] == ["current_page", "data", "last_page", "per_page", "total"]
    assert summary["pagination"]["current_page"] == 1
    assert summary["pagination"]["last_page"] == 3
    assert summary["pagination"]["per_page"] == 25
    assert summary["pagination"]["total"] == 60
    assert summary["pagination"]["next_page_number"] == 2
    assert summary["warnings"] == ["Nested paginator detected under top-level data."]


def test_discovery_summarizes_plain_list_and_single_object_shapes():
    list_summary = summarize_json_shape([{"id": 1, "sku": "SKU-1"}])
    object_summary = summarize_json_shape({"id": 2, "name": "Single"})

    assert list_summary["response_style"] == "plain_list"
    assert list_summary["record_count_in_payload"] == 1
    assert object_summary["response_style"] == "single_object"
    assert object_summary["first_record_keys"] == ["id", "name"]


def test_discovery_detects_pagination_clues():
    clues = pagination_clues(
        {
            "data": [],
            "links": {"next": "https://example.test/page/2"},
        }
    )

    assert clues["detected"] is True
    assert clues["links_keys"] == ["next"]
    assert clues["next_page_number"] == 2


def test_discovery_reports_endpoint_success_without_writes(tmp_path):
    seen_methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_methods.append(request.method)
        return httpx.Response(200, json={"data": [{"id": 1, "sku": "SKU-1"}]})

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    result = discover_endpoint(client, "/products", output_dir=tmp_path)

    assert result["ok"] is True
    assert result["status_code"] == 200
    assert result["content_type"] == "application/json"
    assert result["is_json"] is True
    assert result["endpoint"] == "/products"
    assert result["first_record_keys"] == ["id", "sku"]
    assert seen_methods == ["GET"]
    assert (tmp_path / "products.summary.json").exists()
    assert (tmp_path / "products.first-record.json").exists()
    assert not (tmp_path / "products.raw.json").exists()


def test_discovery_can_fetch_page_2_when_requested():
    seen_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if request.url.params.get("page") == "2":
            return httpx.Response(
                200,
                json={"data": [{"id": 2}], "meta": {"current_page": 2, "last_page": 2}},
            )
        return httpx.Response(
            200,
            json={"data": [{"id": 1}], "meta": {"current_page": 1, "last_page": 2}},
        )

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    result = discover_endpoint(client, "/products", fetch_page_2=True)

    assert result["page_2"]["record_count_in_payload"] == 1
    assert seen_urls == [
        "https://wms.orderpro.cloud/api/v2/products",
        "https://wms.orderpro.cloud/api/v2/products?page=2",
    ]


def test_discovery_summarizes_non_json_response_safely():
    html = "<html><body>" + ("A" * 500) + "</body></html>"
    summary = non_json_summary(html)

    assert summary["response_style"] == "non_json"
    assert summary["text_preview"] == sanitized_text_preview(html)
    assert len(summary["text_preview"]) == 300
    assert summary["warnings"] == ["Non-JSON response."]


def test_discovery_reports_non_json_endpoint_without_raw_save(tmp_path):
    seen_methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_methods.append(request.method)
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><body>Stock count page</body></html>",
        )

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    result = discover_endpoint(client, "https://wms.orderpro.cloud/stock-count", output_dir=tmp_path)

    assert result["ok"] is True
    assert result["content_type"] == "text/html; charset=utf-8"
    assert result["is_json"] is False
    assert result["response_style"] == "non_json"
    assert result["text_preview"] == "<html><body>Stock count page</body></html>"
    assert seen_methods == ["GET"]
    assert (tmp_path / "wms.orderpro.cloud_stock-count.summary.json").exists()
    assert (tmp_path / "wms.orderpro.cloud_stock-count.first-record.json").exists()
    assert not (tmp_path / "wms.orderpro.cloud_stock-count.raw.json").exists()


def test_discovery_reports_endpoint_failure_without_crashing():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not found"})

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    result = discover_endpoint(client, "/unknown")

    assert result == {
        "endpoint": "/unknown",
        "ok": False,
        "status_code": 404,
        "content_type": "application/json",
        "is_json": None,
        "error": "Not found",
    }


def test_warehouse_endpoint_failure_does_not_crash_discovery():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "Server error"})

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    result = discover_endpoint(client, "/warehouses")

    assert result["ok"] is False
    assert result["status_code"] == 500
    assert result["error"] == "Server error"


def test_stock_count_failure_does_not_crash_discovery():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(500, headers={"content-type": "text/html"}, text="Server error")

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    result = discover_endpoint(client, "https://wms.orderpro.cloud/stock-count")

    assert result["ok"] is False
    assert result["status_code"] == 500
    assert result["content_type"] == "text/html"


def test_discovery_sample_filename_is_safe_for_nested_paths():
    assert sample_filename("/purchase-orders") == "purchase-orders.json"
    assert sample_filename("/nested/path") == "nested_path.json"
    assert sample_filename("https://wms.orderpro.cloud/stock-count") == "wms.orderpro.cloud_stock-count.json"


def test_save_sample_files_writes_summary_and_first_record_without_token(tmp_path):
    payload = {
        "data": [
            {
                "id": 1,
                "sku": "SKU-1",
                "access_token": "secret-token",
            }
        ],
        "meta": {"current_page": 1, "last_page": 1},
    }
    summary = summarize_json_shape(payload)

    saved = save_sample_files("/products", payload, summary, output_dir=tmp_path)

    assert sorted(saved) == ["first_record", "summary"]
    assert "secret-token" not in (tmp_path / "products.summary.json").read_text(encoding="utf-8")
    first_record = (tmp_path / "products.first-record.json").read_text(encoding="utf-8")
    assert "SKU-1" in first_record
    assert "secret-token" not in first_record


def test_save_sample_files_only_writes_raw_when_explicitly_requested(tmp_path):
    payload = {"data": [{"id": 1}]}
    summary = summarize_json_shape(payload)

    saved = save_sample_files("/products", payload, summary, output_dir=tmp_path, save_raw=True)

    assert sorted(saved) == ["first_record", "raw", "summary"]
    assert (tmp_path / "products.raw.json").exists()
