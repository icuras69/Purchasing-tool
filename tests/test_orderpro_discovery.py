import httpx

from app.services.orderpro_client import OrderProClient
from scripts.discover_orderpro_api import (
    discover_product_supplier_relationships,
    discover_endpoint,
    inspect_first_inventory_product,
    inspect_first_purchase_order_item,
    non_json_summary,
    pagination_clues,
    product_detail_endpoints,
    response_style,
    scan_supplier_relationship_fields,
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


def test_product_detail_endpoints_include_id_sku_and_supplier_variants():
    endpoints = product_detail_endpoints({"id": 123, "sku": "A/B 123"})

    assert endpoints == [
        "/products/123",
        "/products/123?include=supplier",
        "/products/123?with=supplier",
        "/products/123?relations=supplier",
        "/products/123/supplier",
        "/products/A%2FB%20123",
    ]


def test_supplier_relationship_scanner_detects_supplier_and_purchasing_fields():
    payload = {
        "id": 1,
        "supplier_id": 42,
        "supplier": {"code": "SUP", "name": "Supplier"},
        "supplier_sku": "SUP-SKU",
        "details": {"purchase_price": 9.5, "minimum_order_quantity": 6},
    }

    scan = scan_supplier_relationship_fields(payload)

    assert scan["supplier_fields"]["supplier_id"] == 42
    assert scan["supplier_fields"]["supplier"] == {"type": "object", "keys": ["code", "name"]}
    assert scan["supplier_fields"]["supplier_sku"] == "SUP-SKU"
    assert scan["purchasing_fields"]["details.purchase_price"] == 9.5
    assert scan["purchasing_fields"]["details.minimum_order_quantity"] == 6


def test_supplier_relationship_scanner_handles_missing_fields_cleanly():
    scan = scan_supplier_relationship_fields({"id": 1, "sku": "SKU-1"})

    assert scan == {"supplier_fields": {}, "purchasing_fields": {}}


def test_purchase_order_item_inspection_summarizes_first_item_supplier_clues():
    payload = {
        "data": [
            {
                "id": 1,
                "supplier": {"id": 2, "name": "Supplier"},
                "items": [
                    {
                        "product_id": 10,
                        "sku": "SKU-10",
                        "supplier_sku": "SUP-10",
                        "unit_cost": 5.5,
                        "qty": 3,
                    }
                ],
            }
        ]
    }

    summary = inspect_first_purchase_order_item(payload)

    assert summary["order_keys"] == ["id", "items", "supplier"]
    assert summary["item_keys"] == ["product_id", "qty", "sku", "supplier_sku", "unit_cost"]
    assert summary["item_supplier_scan"]["supplier_fields"]["supplier_sku"] == "SUP-10"
    assert summary["item_supplier_scan"]["purchasing_fields"]["unit_cost"] == 5.5


def test_inventory_product_inspection_detects_nested_product_supplier_fields():
    payload = {
        "data": [
            {
                "warehouse_id": 7,
                "qty": 4,
                "product": {
                    "id": 10,
                    "sku": "SKU-10",
                    "supplier_code": "SUP",
                    "supplier_name": "Supplier",
                },
            }
        ]
    }

    summary = inspect_first_inventory_product(payload)

    assert summary["inventory_row_keys"] == ["product", "qty", "warehouse_id"]
    assert summary["product_keys"] == ["id", "sku", "supplier_code", "supplier_name"]
    assert summary["product_supplier_scan"]["supplier_fields"]["supplier_code"] == "SUP"
    assert summary["product_supplier_scan"]["supplier_fields"]["supplier_name"] == "Supplier"


def test_product_supplier_relationship_discovery_uses_get_only_and_handles_detail_failures():
    seen_methods = []
    seen_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_methods.append(request.method)
        seen_paths.append(request.url.path + (f"?{request.url.query.decode()}" if request.url.query else ""))
        path = request.url.path
        query = request.url.query.decode()
        if path == "/api/v2/products" and not query:
            return httpx.Response(200, json={"data": [{"id": 1, "sku": "SKU-1", "name": "Product"}]})
        if path == "/api/v2/products/1" and query == "include=supplier":
            return httpx.Response(
                200,
                json={"data": {"id": 1, "supplier_id": 42, "supplier": {"id": 42, "name": "Supplier"}}},
            )
        if path == "/api/v2/purchase-orders":
            return httpx.Response(
                200,
                json={"data": [{"id": 5, "items": [{"product_id": 1, "unit_cost": 2.5}]}]},
            )
        if path == "/api/v2/inventory":
            return httpx.Response(
                200,
                json={"data": [{"product": {"id": 1, "sku": "SKU-1"}, "qty": 3}]},
            )
        return httpx.Response(404, json={"message": "Not found"})

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    result = discover_product_supplier_relationships(client, product_limit=1)

    assert set(seen_methods) == {"GET"}
    assert "/api/v2/products/1?include=supplier" in seen_paths
    assert len(result["detail_results"]) == 6
    successful = [row for row in result["detail_results"] if row["ok"]]
    failed = [row for row in result["detail_results"] if not row["ok"]]
    assert successful[0]["supplier_fields"]["data.supplier_id"] == 42
    assert failed
    assert result["purchase_order_item_inspection"]["item_keys"] == ["product_id", "unit_cost"]
    assert result["inventory_product_inspection"]["product_keys"] == ["id", "sku"]
    assert "secret-token" not in str(result)
