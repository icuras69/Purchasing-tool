import logging

from app.models.product import Product
from app.services.product_search import filter_product_rows_by_search


def _orderpro_product(
    db_session,
    *,
    product_id: int,
    name: str,
    sku: str,
    barcode: str | None = None,
    supplier_sku: str | None = None,
    supplier_id: int | None = None,
    is_active: bool = True,
):
    product = Product(
        id=product_id,
        name=name,
        description=f"{name} description",
        source_system="orderpro",
        orderpro_id=f"op-{product_id}",
        orderpro_sku=sku,
        barcode=barcode,
        supplier_sku=supplier_sku,
        supplier_id=supplier_id,
        current_stock=0,
        safety_stock=0,
        lead_time_days=0,
        min_order_qty=0,
        is_active=is_active,
    )
    db_session.add(product)
    db_session.commit()
    return product


def test_product_search_helper_prefers_exact_product_id_over_numeric_sku():
    rows = [
        {"product_id": 3020, "orderpro_sku": "REAL-SKU", "product_name": "Exact Product"},
        {"product_id": 4000, "orderpro_sku": "3020", "product_name": "Numeric SKU"},
    ]

    assert filter_product_rows_by_search(rows, "3020") == [rows[0]]


def test_product_search_helper_does_not_partially_match_identifier_fields():
    rows = [
        {
            "product_id": 7721,
            "orderpro_sku": "4018653020258",
            "barcode": "4018653020258",
            "supplier_sku": "4018653020258",
            "product_name": "Plastic Curry Comb",
        }
    ]

    assert filter_product_rows_by_search(rows, "3020") == []


def test_products_endpoint_prefers_exact_product_id_over_numeric_sku(client, db_session):
    exact = _orderpro_product(db_session, product_id=3020, name="Exact Product", sku="EXACT-SKU")
    _orderpro_product(db_session, product_id=4000, name="Numeric SKU Product", sku="3020")

    response = client.get("/products/?search=3020")

    assert response.status_code == 200
    payload = response.json()
    assert [row["id"] for row in payload] == [exact.id]


def test_products_endpoint_does_not_partially_match_identifier_fields(client, db_session):
    _orderpro_product(
        db_session,
        product_id=7721,
        name="Plastic Curry Comb",
        sku="4018653020258",
        barcode="4018653020258",
        supplier_sku="4018653020258",
    )

    response = client.get("/products/?search=3020")

    assert response.status_code == 200
    assert response.json() == []


def test_products_endpoint_searches_exact_barcode(client, db_session):
    product = _orderpro_product(
        db_session,
        product_id=3100,
        name="Barcode Product",
        sku="BARCODE-SKU",
        barcode="BAR-123",
    )
    _orderpro_product(db_session, product_id=3101, name="Other Product", sku="OTHER-SKU", barcode="OTHER")

    response = client.get("/products/?search=BAR-123")

    assert response.status_code == 200
    payload = response.json()
    assert [row["id"] for row in payload] == [product.id]
    assert payload[0]["barcode"] == "BAR-123"


def test_products_endpoint_hides_inactive_products_but_detail_remains_available(client, db_session):
    active = _orderpro_product(db_session, product_id=3200, name="Active Product", sku="ACTIVE-SKU")
    inactive = _orderpro_product(
        db_session,
        product_id=3201,
        name="Inactive Product",
        sku="INACTIVE-SKU",
        is_active=False,
    )

    list_response = client.get("/products/")
    search_response = client.get("/products/?search=INACTIVE-SKU")
    detail_response = client.get(f"/products/{inactive.id}")

    assert list_response.status_code == 200
    assert [row["id"] for row in list_response.json()] == [active.id]
    assert search_response.status_code == 200
    assert search_response.json() == []
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == inactive.id


def test_forecast_reconciliation_search_prefers_exact_product_id(client, db_session):
    exact = _orderpro_product(db_session, product_id=3020, name="Readiness Exact", sku="READINESS-EXACT")
    _orderpro_product(db_session, product_id=4100, name="Readiness Numeric SKU", sku="3020")

    response = client.get("/api/forecast-reconciliation/products?search=3020")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["product_id"] == exact.id


def test_demand_history_search_prefers_exact_product_id(client, db_session):
    exact = _orderpro_product(db_session, product_id=3020, name="Demand Exact", sku="DEMAND-EXACT")
    _orderpro_product(db_session, product_id=4200, name="Demand Numeric SKU", sku="3020")

    response = client.get("/api/demand-history-reconciliation/products?search=3020")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["product_id"] == exact.id


def test_demand_history_search_does_not_partially_match_identifier_fields(client, db_session):
    _orderpro_product(
        db_session,
        product_id=7721,
        name="Demand Plastic Curry Comb",
        sku="4018653020258",
        barcode="4018653020258",
        supplier_sku="4018653020258",
    )

    response = client.get("/api/demand-history-reconciliation/products?search=3020")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 0
    assert payload["items"] == []


def test_demand_history_search_enriches_only_matching_products(client, db_session, monkeypatch):
    exact = _orderpro_product(db_session, product_id=3020, name="Demand Exact", sku="DEMAND-EXACT")
    other = _orderpro_product(db_session, product_id=4200, name="Demand Other", sku="DEMAND-OTHER")
    evaluated_product_ids = []

    def fake_readiness(_db, product):
        evaluated_product_ids.append(product.id)
        return {
            "readiness_status": "monitor_only",
            "readiness_score": 50,
            "missing_inputs": ["demand_history"],
            "demand_source": "none",
        }

    monkeypatch.setattr(
        "app.services.demand_history_reconciliation.evaluate_product_readiness",
        fake_readiness,
    )

    response = client.get("/api/demand-history-reconciliation/products?search=3020")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["product_id"] == exact.id
    assert evaluated_product_ids == [exact.id]
    assert other.id not in evaluated_product_ids


def test_manual_supplier_cleanup_search_prefers_exact_product_id(client, db_session):
    exact = _orderpro_product(db_session, product_id=3020, name="Cleanup Exact", sku="CLEANUP-EXACT")
    _orderpro_product(db_session, product_id=4300, name="Cleanup Numeric SKU", sku="3020")

    response = client.get("/api/manual-supplier-cleanup/candidates?search=3020")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["product_id"] == exact.id


def test_manual_supplier_cleanup_search_does_not_partially_match_identifier_fields(client, db_session):
    _orderpro_product(
        db_session,
        product_id=7721,
        name="Cleanup Plastic Curry Comb",
        sku="4018653020258",
        barcode="4018653020258",
        supplier_sku="4018653020258",
    )

    response = client.get("/api/manual-supplier-cleanup/candidates?search=3020")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 0
    assert payload["items"] == []


def test_manual_supplier_cleanup_search_builds_only_matching_candidate_rows(client, db_session, monkeypatch):
    exact = _orderpro_product(db_session, product_id=3020, name="Cleanup Exact", sku="CLEANUP-EXACT")
    other = _orderpro_product(db_session, product_id=4300, name="Cleanup Other", sku="CLEANUP-OTHER")
    built_product_ids = []

    def fake_cleanup_row(_db, product):
        built_product_ids.append(product.id)
        return {
            "product_id": product.id,
            "orderpro_id": product.orderpro_id,
            "orderpro_sku": product.orderpro_sku,
            "product_name": product.name,
            "barcode": product.barcode,
            "description": product.description,
            "current_stock": 0,
            "demand_history_available": False,
            "open_customer_demand": 0,
            "cost_price": None,
            "priority_score": 0,
            "existing_suggested_supplier_id": None,
        }

    monkeypatch.setattr("app.services.manual_supplier_cleanup._cleanup_row_for_product", fake_cleanup_row)

    response = client.get("/api/manual-supplier-cleanup/candidates?search=3020")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["product_id"] == exact.id
    assert built_product_ids == [exact.id]
    assert other.id not in built_product_ids


def test_seasonal_products_search_prefers_exact_product_id(client, db_session):
    exact = _orderpro_product(db_session, product_id=3020, name="Seasonal Exact", sku="SEASONAL-EXACT")
    _orderpro_product(db_session, product_id=4400, name="Seasonal Numeric SKU", sku="3020")

    response = client.get("/products/seasonal?search=3020")

    assert response.status_code == 200
    payload = response.json()
    assert [row["product_id"] for row in payload] == [exact.id]


def test_seasonal_products_search_does_not_partially_match_identifier_fields(client, db_session):
    _orderpro_product(
        db_session,
        product_id=7721,
        name="Seasonal Plastic Curry Comb",
        sku="4018653020258",
        barcode="4018653020258",
        supplier_sku="4018653020258",
    )

    response = client.get("/products/seasonal?search=3020")

    assert response.status_code == 200
    assert response.json() == []


def test_forecast_readiness_search_audits_only_matching_products(client, db_session, monkeypatch):
    exact = _orderpro_product(db_session, product_id=3020, name="Readiness Exact", sku="READINESS-EXACT")
    other = _orderpro_product(db_session, product_id=4400, name="Readiness Other", sku="READINESS-OTHER")
    audited_product_ids = []

    def fake_audit(_db, product):
        audited_product_ids.append(product.id)
        return {
            "product_id": product.id,
            "orderpro_sku": product.orderpro_sku,
            "product_name": product.name,
            "blocking_issues": [],
            "warning_issues": [],
            "missing_inputs": [],
            "moq_source": "product_record",
            "cost_source": "missing",
            "seasonality_readiness_status": None,
        }

    monkeypatch.setattr("app.services.seasonality_backtesting.audit_product_forecast_inputs", fake_audit)

    response = client.get("/products/forecast-readiness?search=3020")

    assert response.status_code == 200
    assert [row["product_id"] for row in response.json()] == [exact.id]
    assert audited_product_ids == [exact.id]
    assert other.id not in audited_product_ids


def test_perf_log_is_emitted_for_baseline_endpoint(client, db_session, caplog):
    _orderpro_product(db_session, product_id=5000, name="Perf Product", sku="PERF-SKU")

    with caplog.at_level(logging.INFO, logger="app.performance"):
        response = client.get("/api/manual-supplier-cleanup/summary")

    assert response.status_code == 200
    assert any("PERF manual_supplier_cleanup.summary" in record.message for record in caplog.records)
