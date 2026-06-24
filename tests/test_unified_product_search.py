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
        is_active=True,
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


def test_products_endpoint_prefers_exact_product_id_over_numeric_sku(client, db_session):
    exact = _orderpro_product(db_session, product_id=3020, name="Exact Product", sku="EXACT-SKU")
    _orderpro_product(db_session, product_id=4000, name="Numeric SKU Product", sku="3020")

    response = client.get("/products/?search=3020")

    assert response.status_code == 200
    payload = response.json()
    assert [row["id"] for row in payload] == [exact.id]


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


def test_manual_supplier_cleanup_search_prefers_exact_product_id(client, db_session):
    exact = _orderpro_product(db_session, product_id=3020, name="Cleanup Exact", sku="CLEANUP-EXACT")
    _orderpro_product(db_session, product_id=4300, name="Cleanup Numeric SKU", sku="3020")

    response = client.get("/api/manual-supplier-cleanup/candidates?search=3020")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["product_id"] == exact.id


def test_seasonal_products_search_prefers_exact_product_id(client, db_session):
    exact = _orderpro_product(db_session, product_id=3020, name="Seasonal Exact", sku="SEASONAL-EXACT")
    _orderpro_product(db_session, product_id=4400, name="Seasonal Numeric SKU", sku="3020")

    response = client.get("/products/seasonal?search=3020")

    assert response.status_code == 200
    payload = response.json()
    assert [row["product_id"] for row in payload] == [exact.id]


def test_perf_log_is_emitted_for_baseline_endpoint(client, db_session, caplog):
    _orderpro_product(db_session, product_id=5000, name="Perf Product", sku="PERF-SKU")

    with caplog.at_level(logging.INFO, logger="app.performance"):
        response = client.get("/api/manual-supplier-cleanup/summary")

    assert response.status_code == 200
    assert any("PERF manual_supplier_cleanup.summary" in record.message for record in caplog.records)
