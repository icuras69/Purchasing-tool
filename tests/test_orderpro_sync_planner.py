import httpx

from app.models.inventory_position import InventoryPosition
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse
from app.services.orderpro_client import OrderProClient
from app.services.orderpro_sync_planner import (
    fetch_orderpro_records,
    load_product_csv,
    plan_inventory_sync,
    plan_orderpro_sync,
    plan_product_sync,
    plan_supplier_sync,
)
from scripts.plan_orderpro_sync import current_utc_timestamp_for_filename, print_report


def test_supplier_planning_reports_create_update_and_match(db_session):
    matching = Supplier(
        name="Matched Supplier",
        normalized_name="matched supplier",
        orderpro_id="1",
        orderpro_code="SUP1",
        email="match@example.test",
        phone="111",
        source_system="orderpro",
    )
    needs_update = Supplier(
        name="Old Name",
        normalized_name="old name",
        orderpro_id="2",
        orderpro_code="SUP2",
        email="old@example.test",
        phone="222",
        source_system="local",
    )
    local_only = Supplier(
        name="Local Only",
        normalized_name="local only",
        orderpro_id="99",
        orderpro_code="OLD",
    )
    db_session.add_all([matching, needs_update, local_only])
    db_session.flush()

    report = plan_supplier_sync(
        db_session,
        [
            {"id": 1, "code": "SUP1", "name": "Matched Supplier", "email": "match@example.test", "phone": "111", "is_active": True},
            {"id": 2, "code": "SUP2", "name": "New Name", "email": "new@example.test", "phone": "222", "is_active": True},
            {"id": 3, "code": "SUP3", "name": "New Supplier", "email": "new3@example.test", "phone": "333", "is_active": True},
            {"name": "Missing Identity"},
        ],
    )

    assert report["summary"]["to_create"] == 1
    assert report["summary"]["to_update"] == 1
    assert report["summary"]["already_matching"] == 1
    assert report["summary"]["missing_code_or_id"] == 1
    assert report["summary"]["local_not_found_in_orderpro"] == 1
    assert report["to_update"][0]["changes"]["name"]["desired"] == "New Name"


def test_product_planning_maps_csv_supplier_code_and_reports_missing_or_unknown_codes(db_session):
    supplier = Supplier(
        name="Supplier One",
        normalized_name="supplier one",
        orderpro_id="10",
        orderpro_code="SUP1",
        source_system="orderpro",
    )
    matching_product = Product(
        name="Existing Product",
        source_key="SKU-1",
        orderpro_id="1",
        orderpro_sku="SKU-1",
        supplier_id=None,
        supplier_sku="SUP-SKU-1",
        source_system="orderpro",
    )
    update_product = Product(
        name="Old Product",
        source_key="SKU-2",
        orderpro_id="2",
        orderpro_sku="SKU-2",
        source_system="local",
    )
    db_session.add_all([supplier, matching_product, update_product])
    db_session.flush()

    rows = {
        "SKU-1": {"sku": "SKU-1", "supplier_code": "SUP1", "supplier_sku": "SUP-SKU-1"},
        "SKU-2": {"sku": "SKU-2", "supplier_code": "SUP1", "supplier_sku": "SUP-SKU-2"},
        "SKU-3": {"sku": "SKU-3", "supplier_code": "", "supplier_sku": ""},
        "SKU-4": {"sku": "SKU-4", "supplier_code": "UNKNOWN", "supplier_sku": "SUP-SKU-4"},
    }
    products = [
        {"id": 1, "sku": "SKU-1", "name": "Existing Product", "is_active": True},
        {"id": 2, "sku": "SKU-2", "name": "New Product Name", "is_active": True},
        {"id": 3, "sku": "SKU-3", "name": "No Supplier Code", "is_active": True},
        {"id": 4, "sku": "SKU-4", "name": "Unknown Supplier", "is_active": True},
        {"id": 5, "sku": "SKU-5", "name": "Missing CSV", "is_active": True},
    ]
    suppliers = [{"id": 10, "code": "SUP1", "name": "Supplier One"}]

    report = plan_product_sync(db_session, products, rows, suppliers)

    assert report["summary"]["to_create"] == 3
    assert report["summary"]["to_update"] == 2
    assert report["summary"]["missing_from_csv"] == 1
    assert report["summary"]["csv_rows_missing_supplier_code"] == 1
    assert report["summary"]["unknown_supplier_codes"] == 1
    assert report["summary"]["would_assign_supplier"] == 2
    assert report["summary"]["would_remain_without_supplier"] == 3
    assert report["summary"]["unknown_supplier_code_check_used_full_supplier_list"] is True
    update_changes = {row["orderpro_sku"]: row["changes"] for row in report["to_update"]}
    assert update_changes["SKU-2"]["supplier_id"]["desired"] == supplier.id
    assert report["unknown_supplier_codes"] == [{"sku": "SKU-4", "supplier_code": "UNKNOWN"}]
    assert report["unknown_supplier_code_samples"] == [{"supplier_code": "UNKNOWN", "sample_skus": ["SKU-4"]}]
    assert report["csv_rows_missing_supplier_code_sample"] == [
        {"orderpro_id": "3", "sku": "SKU-3", "name": "No Supplier Code"}
    ]


def test_unknown_supplier_code_not_reported_when_supplier_exists_on_page_two(db_session):
    report = plan_product_sync(
        db_session,
        [{"id": 1, "sku": "SKU-1", "name": "Product", "is_active": True}],
        {"SKU-1": {"sku": "SKU-1", "supplier_code": "PAGE2", "supplier_sku": "SUP-SKU"}},
        [
            {"id": 10, "code": "PAGE1", "name": "First Page Supplier"},
            {"id": 11, "code": "PAGE2", "name": "Second Page Supplier"},
        ],
    )

    assert report["summary"]["unknown_supplier_codes"] == 0
    assert report["unknown_supplier_codes"] == []


def test_limited_supplier_pages_marks_unknown_supplier_codes_as_unreliable(db_session):
    report = plan_product_sync(
        db_session,
        [{"id": 1, "sku": "SKU-1", "name": "Product", "is_active": True}],
        {"SKU-1": {"sku": "SKU-1", "supplier_code": "MAYBE_PAGE2", "supplier_sku": "SUP-SKU"}},
        [{"id": 10, "code": "PAGE1", "name": "First Page Supplier"}],
        supplier_pages_limited=True,
    )

    assert report["summary"]["unknown_supplier_code_check_used_full_supplier_list"] is False
    assert "may be unreliable" in " ".join(report["warnings"])


def test_inventory_planning_derives_warehouse_and_reports_missing_product(db_session):
    product = Product(name="Product", source_key="SKU-1", orderpro_id="1", orderpro_sku="SKU-1")
    warehouse = Warehouse(orderpro_id="W1", name="Old Warehouse", source_system="orderpro")
    db_session.add_all([product, warehouse])
    db_session.flush()
    position = InventoryPosition(
        product_id=product.id,
        warehouse_id=warehouse.id,
        orderpro_product_id="1",
        orderpro_warehouse_id="W1",
        location_id="L1",
        lot_id="LOT1",
        quantity_on_hand=1,
        available=1,
        on_hand=1,
    )
    db_session.add(position)
    db_session.flush()

    report = plan_inventory_sync(
        db_session,
        [
            {
                "product_id": 1,
                "product": {"sku": "SKU-1"},
                "warehouse_id": "W1",
                "warehouse": {"name": "Main Warehouse", "code": "MAIN"},
                "location_id": "L1",
                "location": {"name": "Aisle 1"},
                "lot_id": "LOT1",
                "lot": "Lot 1",
                "qty": 5,
            },
            {
                "product_id": 1,
                "product": {"sku": "SKU-1"},
                "warehouse_id": "W2",
                "warehouse": {"name": "Second Warehouse"},
                "location_id": "L2",
                "qty": 3,
            },
            {"product_id": 999, "product": {"sku": "NOPE"}, "warehouse_id": "W1", "qty": 8},
            {"product_id": 1, "product": {"sku": "SKU-1"}, "qty": 2},
        ],
    )

    assert report["summary"]["warehouses_to_create"] == 1
    assert report["summary"]["warehouses_to_update"] == 1
    assert report["summary"]["inventory_positions_to_create"] == 1
    assert report["summary"]["inventory_positions_to_update"] == 1
    assert report["summary"]["rows_missing_product_match"] == 1
    assert report["summary"]["rows_missing_warehouse_id"] == 1
    assert report["summary"]["rows_with_derivable_warehouse_missing_name"] == 1
    assert report["total_stock_by_local_product_id"][str(product.id)] == 8
    assert report["total_stock_by_orderpro_product_id"]["1"] == 8


def test_inventory_planning_matches_product_planned_for_creation_and_derives_warehouse(db_session):
    report = plan_inventory_sync(
        db_session,
        [
            {
                "product_id": 100,
                "product": {"sku": "SKU-100"},
                "warehouse_id": "W100",
                "warehouse": {"name": "Planned Warehouse"},
                "location_id": "L1",
                "qty": 7,
            },
            {
                "product_id": 101,
                "product": {"sku": "SKU-101"},
                "warehouse_id": "W101",
                "qty": 4,
            },
        ],
        planned_products=[
            {"id": 100, "sku": "SKU-100", "name": "Planned Product"},
            {"id": 101, "sku": "SKU-101", "name": "Planned Product 2"},
        ],
    )

    assert report["summary"]["rows_missing_product_match"] == 0
    assert report["summary"]["warehouses_to_create"] == 2
    assert report["summary"]["inventory_positions_to_create"] == 2
    assert report["inventory_positions_to_create"][0]["planned_product"] is True
    assert report["inventory_positions_to_create"][0]["product_id"] is None
    assert report["summary"]["rows_with_derivable_warehouse_missing_name"] == 1
    assert report["warehouses_to_create"][1]["name"] == "OrderPro Warehouse W101"


def test_orderpro_sync_plan_is_dry_run_and_does_not_commit_database_changes(db_session):
    supplier = Supplier(
        name="Supplier One",
        normalized_name="supplier one",
        orderpro_id="10",
        orderpro_code="SUP1",
    )
    db_session.add(supplier)
    db_session.flush()

    report = plan_orderpro_sync(
        db_session,
        suppliers=[{"id": 10, "code": "SUP1", "name": "Supplier One"}],
        products=[{"id": 1, "sku": "SKU-1", "name": "New Product", "is_active": True}],
        product_csv_rows={"SKU-1": {"sku": "SKU-1", "supplier_code": "SUP1", "supplier_sku": "SUP-SKU-1"}},
        inventory=None,
    )

    assert report["mode"] == "dry_run"
    assert report["products"]["summary"]["to_create"] == 1
    assert db_session.query(Product).count() == 0
    assert db_session.query(Supplier).count() == 1


def test_load_product_csv_indexes_rows_by_sku(tmp_path):
    csv_path = tmp_path / "products.csv"
    csv_path.write_text(
        "sku,name,supplier_code,supplier_sku\nSKU-1,Product One,SUP1,SUP-SKU-1\n",
        encoding="utf-8",
    )

    rows = load_product_csv(csv_path)

    assert rows["SKU-1"]["supplier_code"] == "SUP1"
    assert rows["SKU-1"]["supplier_sku"] == "SUP-SKU-1"


def test_fetch_orderpro_records_respects_limit_pages_and_uses_get_only():
    seen_methods = []
    seen_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_methods.append(request.method)
        seen_urls.append(str(request.url))
        page = request.url.params.get("page")
        if page == "2":
            return httpx.Response(200, json={"data": [{"id": 2}], "meta": {"current_page": 2, "last_page": 3}})
        return httpx.Response(200, json={"data": [{"id": 1}], "meta": {"current_page": 1, "last_page": 3}})

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    records = fetch_orderpro_records(client, "/products", limit_pages=2)

    assert records == [{"id": 1}, {"id": 2}]
    assert seen_methods == ["GET", "GET"]
    assert seen_urls == [
        "https://wms.orderpro.cloud/api/v2/products?page=1",
        "https://wms.orderpro.cloud/api/v2/products?page=2",
    ]


def test_fetch_orderpro_records_fetches_all_pages_when_no_limit():
    seen_pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        seen_pages.append(page)
        return httpx.Response(
            200,
            json={"data": [{"id": page}], "meta": {"current_page": page, "last_page": 2}},
        )

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    records = fetch_orderpro_records(client, "/suppliers")

    assert records == [{"id": 1}, {"id": 2}]
    assert seen_pages == [1, 2]


def test_dry_run_report_does_not_print_tokens(capsys, db_session):
    report = plan_orderpro_sync(
        db_session,
        suppliers=[{"id": 1, "code": "SUP1", "name": "Supplier", "api_token": "secret-token"}],
        products=[{"id": 1, "sku": "SKU-1", "name": "Product", "api_token": "secret-token"}],
        product_csv_rows={"SKU-1": {"sku": "SKU-1", "supplier_code": "SUP1", "supplier_sku": "SUP-SKU"}},
        inventory=None,
    )

    print_report(report)
    output = capsys.readouterr().out

    assert "secret-token" not in str(report)
    assert "secret-token" not in output


def test_current_utc_timestamp_for_filename_is_timezone_aware(monkeypatch):
    class FakeDateTime:
        @classmethod
        def now(cls, tz):
            assert tz is not None

            class FakeNow:
                def strftime(self, _format):
                    return "20260529_120000"

            return FakeNow()

    monkeypatch.setattr("scripts.plan_orderpro_sync.datetime", FakeDateTime)

    assert current_utc_timestamp_for_filename() == "20260529_120000"
