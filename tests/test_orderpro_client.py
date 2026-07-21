from datetime import datetime, timezone

import httpx
import pytest

from app.services.orderpro_client import (
    OrderProClient,
    OrderProConfigError,
    OrderProHTTPError,
    OrderProTimeoutError,
    extract_records,
    next_page_number,
    normalize_path,
    retry_after_seconds,
)


def test_orderpro_client_uses_bearer_auth_and_builds_correct_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"data": [{"id": 1, "sku": "SKU-1"}]})

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    payload = client.generic_get("/products")

    assert payload == {"data": [{"id": 1, "sku": "SKU-1"}]}
    assert seen == {
        "method": "GET",
        "url": "https://wms.orderpro.cloud/api/v2/products",
        "authorization": "Bearer secret-token",
    }


def test_orderpro_client_redacts_token_from_non_200_errors():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Invalid token secret-token"})

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(OrderProHTTPError) as error:
        client.generic_get("/products")

    assert error.value.status_code == 401
    assert "secret-token" not in str(error.value)
    assert "[redacted]" in str(error.value)


def test_orderpro_client_handles_timeout_cleanly():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(OrderProTimeoutError) as error:
        client.generic_get("/products")

    assert "timed out" in str(error.value)
    assert "secret-token" not in str(error.value)


def test_orderpro_client_supports_basic_pagination():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page")
        calls.append((page, request.url.params.get("per_page")))
        if page == "1":
            return httpx.Response(
                200,
                json={
                    "data": [{"id": 1}],
                    "meta": {"current_page": 1, "last_page": 2},
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [{"id": 2}],
                "meta": {"current_page": 2, "last_page": 2},
            },
        )

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    assert client.get_products() == [{"id": 1}, {"id": 2}]
    assert calls == [("1", "200"), ("2", "200")]


def test_orderpro_client_supports_nested_paginator_pagination():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page")
        calls.append((page, request.url.params.get("per_page")))
        if page == "1":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "current_page": 1,
                        "data": [{"id": 1}],
                        "last_page": 2,
                        "per_page": 15,
                        "total": 2,
                    },
                    "meta": {"note": "nested"},
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "current_page": 2,
                    "data": [{"id": 2}],
                    "last_page": 2,
                    "per_page": 15,
                    "total": 2,
                },
            },
        )

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    assert client.get_suppliers() == [{"id": 1}, {"id": 2}]
    assert calls == [("1", "200"), ("2", "200")]


def test_orderpro_client_retries_one_429_then_succeeds_without_duplicate_rows():
    seen_pages = []
    sleeps = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page")
        seen_pages.append(page)
        if seen_pages == ["1"]:
            return httpx.Response(
                200,
                json={"data": [{"id": 1}], "meta": {"current_page": 1, "last_page": 2}},
            )
        if seen_pages == ["1", "2"]:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={"message": "Too many attempts."})
        return httpx.Response(
            200,
            json={"data": [{"id": 2}], "meta": {"current_page": 2, "last_page": 2}},
        )

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
        rate_limit_max_retries=1,
        sleep=sleeps.append,
    )

    assert client._get_all_pages("/orders") == [{"id": 1}, {"id": 2}]
    assert seen_pages == ["1", "2", "2"]
    assert sleeps == [2.0]


def test_orderpro_client_parses_retry_after_http_date():
    retry_at = "Mon, 20 Jul 2026 12:00:05 GMT"
    now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)

    assert retry_after_seconds(retry_at, now=now) == 5.0


def test_orderpro_client_exhausts_429_retry_limit_and_redacts_token():
    calls = []
    sleeps = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            429,
            headers={"Retry-After": "1"},
            json={"message": "Slow down secret-token"},
        )

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
        rate_limit_max_retries=2,
        sleep=sleeps.append,
    )

    with pytest.raises(OrderProHTTPError) as error:
        client.generic_get("/orders")

    assert error.value.status_code == 429
    assert len(calls) == 3
    assert sleeps == [1.0, 1.0]
    assert "secret-token" not in str(error.value)
    assert "[redacted]" in str(error.value)


@pytest.mark.parametrize("status_code", [401, 403, 404, 500])
def test_orderpro_client_does_not_retry_non_429_statuses(status_code):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(status_code, json={"message": f"status {status_code}"})

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
        rate_limit_max_retries=3,
        sleep=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep should not run")),
    )

    with pytest.raises(OrderProHTTPError) as error:
        client.generic_get("/products")

    assert error.value.status_code == status_code
    assert len(calls) == 1


def test_orderpro_client_exposes_get_only_public_api_for_orderpro_calls():
    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=[])),
    )

    assert hasattr(client, "generic_get")
    assert hasattr(client, "get_products")
    assert not hasattr(client, "post")
    assert not hasattr(client, "patch")
    assert not hasattr(client, "delete")
    assert not hasattr(client, "put")


def test_orderpro_client_accepts_same_host_full_url_and_sends_bearer_auth():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html>Stock count</html>")

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    page = client.generic_get_raw("https://wms.orderpro.cloud/stock-count")

    assert page.is_json is False
    assert page.text == "<html>Stock count</html>"
    assert seen == {
        "url": "https://wms.orderpro.cloud/stock-count",
        "authorization": "Bearer secret-token",
    }


def test_orderpro_client_rejects_unknown_external_full_url_by_default():
    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
    )

    with pytest.raises(OrderProConfigError):
        client.generic_get_raw("https://example.test/stock-count")


def test_orderpro_client_maps_root_api_paths_to_configured_host():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": []})

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    client.generic_get_raw("/api/v2/stock-count")

    assert seen["url"] == "https://wms.orderpro.cloud/api/v2/stock-count"


def test_orderpro_payload_helpers_handle_common_shapes():
    assert normalize_path("products") == "/products"
    assert extract_records({"data": [{"id": 1}]}) == [{"id": 1}]
    assert extract_records({"data": {"current_page": 1, "data": [{"id": 2}]}}) == [{"id": 2}]
    assert extract_records([{"id": 1}]) == [{"id": 1}]
    assert extract_records({"id": 1}) == [{"id": 1}]
    assert next_page_number(
        {"data": [], "meta": {"current_page": 1, "last_page": 2}},
        current_page=1,
    ) == 2
    assert next_page_number(
        {"data": {"current_page": 1, "data": [], "last_page": 2}},
        current_page=1,
    ) == 2
    assert next_page_number({"data": []}, current_page=1) is None
