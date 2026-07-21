from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
from typing import Any, Callable

import httpx

from app.core.config import settings

ORDERPRO_COLLECTION_PER_PAGE = 200


class OrderProClientError(Exception):
    pass


class OrderProConfigError(OrderProClientError):
    pass


class OrderProHTTPError(OrderProClientError):
    def __init__(self, path: str, status_code: int, message: str, content_type: str | None = None):
        super().__init__(f"OrderPro GET {path} failed with status {status_code}: {message}")
        self.path = path
        self.status_code = status_code
        self.message = message
        self.content_type = content_type


class OrderProTimeoutError(OrderProClientError):
    pass


@dataclass
class OrderProPage:
    path: str
    status_code: int
    payload: Any


@dataclass
class OrderProRawPage:
    target: str
    url: str
    status_code: int
    content_type: str
    is_json: bool
    payload: Any | None = None
    text: str | None = None


class OrderProClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout_seconds: int | None = None,
        transport: httpx.BaseTransport | None = None,
        rate_limit_max_retries: int | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.base_url = (base_url if base_url is not None else settings.orderpro_api_base_url).rstrip("/")
        self.token = token if token is not None else settings.orderpro_api_token
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.orderpro_timeout_seconds
        self.transport = transport
        configured_retries = (
            rate_limit_max_retries
            if rate_limit_max_retries is not None
            else settings.orderpro_rate_limit_max_retries
        )
        self.rate_limit_max_retries = max(int(configured_retries), 0)
        self.sleep = sleep if sleep is not None else time.sleep

        if not self.base_url:
            raise OrderProConfigError("ORDERPRO_API_BASE_URL is required.")
        if not self.token:
            raise OrderProConfigError("ORDERPRO_API_TOKEN is required.")

    def generic_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._get_page(path, params=params).payload

    def generic_get_raw(
        self,
        target: str,
        params: dict[str, Any] | None = None,
        *,
        allow_external_url: bool = False,
    ) -> OrderProRawPage:
        return self._get_raw_page(target, params=params, allow_external_url=allow_external_url)

    def get_products(self) -> list[Any]:
        return self._get_all_pages("/products")

    def get_suppliers(self) -> list[Any]:
        return self._get_all_pages("/suppliers")

    def get_inventory(self) -> list[Any]:
        return self._get_all_pages("/inventory")

    def get_warehouses(self) -> list[Any]:
        return self._get_all_pages("/warehouses")

    def get_purchase_orders(self) -> list[Any]:
        return self._get_all_pages("/purchase-orders")

    def _get_page(self, path: str, params: dict[str, Any] | None = None) -> OrderProPage:
        raw_page = self._get_raw_page(path, params=params)
        if not raw_page.is_json:
            raise OrderProClientError(f"OrderPro GET {raw_page.target} returned non-JSON content.")

        return OrderProPage(path=normalize_target_label(path), status_code=raw_page.status_code, payload=raw_page.payload)

    def _get_raw_page(
        self,
        target: str,
        params: dict[str, Any] | None = None,
        *,
        allow_external_url: bool = False,
    ) -> OrderProRawPage:
        request_url, send_auth = self._build_request_url(target, allow_external_url=allow_external_url)
        headers = {"Accept": "application/json"}
        if send_auth:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = self._get_with_rate_limit_retries(client, request_url, headers=headers, params=params)
        except httpx.TimeoutException as error:
            raise OrderProTimeoutError(f"OrderPro GET {normalize_target_label(target)} timed out.") from error
        except httpx.HTTPError as error:
            raise OrderProClientError(f"OrderPro GET {normalize_target_label(target)} failed: {type(error).__name__}") from error

        content_type = response.headers.get("content-type", "")
        if response.status_code < 200 or response.status_code >= 300:
            raise OrderProHTTPError(
                normalize_target_label(target),
                response.status_code,
                extract_error_message(response, token=self.token),
                content_type=content_type,
            )

        is_json = response_is_json(content_type)
        if not is_json:
            return OrderProRawPage(
                target=normalize_target_label(target),
                url=str(response.url),
                status_code=response.status_code,
                content_type=content_type,
                is_json=False,
                text=response.text,
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise OrderProClientError(f"OrderPro GET {normalize_target_label(target)} returned invalid JSON.") from error

        return OrderProRawPage(
            target=normalize_target_label(target),
            url=str(response.url),
            status_code=response.status_code,
            content_type=content_type,
            is_json=True,
            payload=payload,
        )

    def _build_request_url(self, target: str, *, allow_external_url: bool = False) -> tuple[str, bool]:
        cleaned = (target or "").strip()
        if not cleaned:
            raise ValueError("OrderPro path or URL is required.")

        base = httpx.URL(self.base_url)
        if cleaned.startswith(("http://", "https://")):
            url = httpx.URL(cleaned)
            if url.host != base.host:
                if not allow_external_url:
                    raise OrderProConfigError("Refusing to call non-OrderPro host.")
                return str(url), False
            return str(url), True

        if cleaned.startswith("/api/"):
            return str(base.copy_with(path=cleaned, query=None)), True

        return f"{self.base_url}{normalize_path(cleaned)}", True

    def _get_all_pages(self, path: str) -> list[Any]:
        page = 1
        rows: list[Any] = []

        while True:
            payload = self.generic_get(path, params=paginated_params(page))
            rows.extend(extract_records(payload))

            next_page = next_page_number(payload, current_page=page)
            if next_page is None:
                break
            page = next_page

        return rows

    def _get_with_rate_limit_retries(
        self,
        client: httpx.Client,
        request_url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None,
    ) -> httpx.Response:
        attempts = 0
        while True:
            response = client.get(request_url, headers=headers, params=params)
            if response.status_code != 429 or attempts >= self.rate_limit_max_retries:
                return response
            attempts += 1
            self.sleep(retry_after_seconds(response.headers.get("Retry-After")))


def paginated_params(page: int) -> dict[str, int]:
    return {"page": page, "per_page": ORDERPRO_COLLECTION_PER_PAGE}


def normalize_path(path: str) -> str:
    cleaned = (path or "").strip()
    if not cleaned:
        raise ValueError("OrderPro path is required.")
    return cleaned if cleaned.startswith("/") else f"/{cleaned}"


def normalize_target_label(target: str) -> str:
    cleaned = (target or "").strip()
    if cleaned.startswith(("http://", "https://")):
        return cleaned
    return normalize_path(cleaned)


def response_is_json(content_type: str) -> bool:
    return "json" in (content_type or "").lower()


def extract_records(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            nested_data = data.get("data")
            if isinstance(nested_data, list):
                return nested_data
            return [data]
    return [payload]


def next_page_number(payload: Any, *, current_page: int) -> int | None:
    if not isinstance(payload, dict):
        return None

    nested_paginator = payload.get("data")
    if isinstance(nested_paginator, dict):
        nested_next_page = next_page_number(nested_paginator, current_page=current_page)
        if nested_next_page is not None:
            return nested_next_page

    meta = payload.get("meta")
    if isinstance(meta, dict):
        current = meta.get("current_page", current_page)
        last = meta.get("last_page")
        try:
            if last is not None and int(current) < int(last):
                return int(current) + 1
        except (TypeError, ValueError):
            return None

    links = payload.get("links")
    if isinstance(links, dict) and links.get("next"):
        return current_page + 1

    if payload.get("next_page_url"):
        return current_page + 1

    current = payload.get("current_page", current_page)
    last = payload.get("last_page")
    try:
        if last is not None and int(current) < int(last):
            return int(current) + 1
    except (TypeError, ValueError):
        return None

    return None


def retry_after_seconds(value: str | None, *, now: datetime | None = None) -> float:
    if not value:
        return 0.0
    cleaned = value.strip()
    try:
        return max(float(cleaned), 0.0)
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(cleaned)
    except (TypeError, ValueError, IndexError, OverflowError):
        return 0.0
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return max((retry_at - reference).total_seconds(), 0.0)


def extract_error_message(response: httpx.Response, *, token: str | None = None) -> str:
    try:
        payload = response.json()
    except ValueError:
        message = response.text[:500] if response.text else "No response body."
        return redact_secret(message, token)

    if isinstance(payload, dict):
        detail = payload.get("message") or payload.get("error") or payload.get("detail")
        if detail:
            return redact_secret(str(detail), token)
    return "Unexpected OrderPro error response."


def redact_secret(message: str, secret: str | None) -> str:
    if not secret:
        return message
    return message.replace(secret, "[redacted]")
