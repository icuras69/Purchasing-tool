import httpx
import pytest

from app.models.inventory_position import InventoryPosition
from app.models.orderpro_order import OrderProOrder, OrderProOrderItem
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse
from app.services.orderpro_client import OrderProClient
from app.services.orderpro_sync_planner import (
    apply_orderpro_supplier_product_sync,
    desired_order_item_fields,
    fetch_orderpro_records,
    fetch_orderpro_records_with_status,
    load_product_csv,
    order_quantity_diagnostics,
    plan_order_sync,
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


def test_supplier_planning_matches_existing_supplier_by_normalized_name(db_session):
    local = Supplier(
        name="Acravet Ltd",
        normalized_name="acravet ltd",
        notes="Keep these notes",
        lead_time_days=14,
    )
    db_session.add(local)
    db_session.flush()

    report = plan_supplier_sync(
        db_session,
        [{"id": 55, "code": "ACR", "name": "Acravet Ltd", "email": "sales@example.test", "phone": "555"}],
    )

    assert report["summary"]["to_create"] == 0
    assert report["summary"]["to_update"] == 1
    assert report["summary"]["matched_by_name"] == 1
    assert report["summary"]["linked_existing_by_name"] == 1
    assert report["matched_by_name"][0]["local_id"] == local.id
    assert report["matched_by_name"][0]["changes"]["orderpro_id"]["desired"] == "55"


def test_supplier_planning_links_edf_man_alias_and_preserves_lead_time(db_session):
    local = Supplier(
        name="ED&F Man",
        normalized_name="ED&F MAN",
        lead_time_days=7,
    )
    db_session.add(local)
    db_session.flush()

    report = plan_supplier_sync(
        db_session,
        [{"id": 18, "code": "ED&FMAN", "name": "EDF Man"}],
    )

    assert report["summary"]["to_create"] == 0
    assert report["summary"]["matched_by_name"] == 1
    assert report["matched_by_name"][0]["local_id"] == local.id
    assert local.lead_time_days == 7


def test_product_csv_normalizes_purchasing_headers_and_rejects_duplicate_skus(tmp_path):
    path = tmp_path / "products.csv"
    path.write_text(
        "SKU,Supplier Code,Lead_time,Cost Price,Minimum Order Quantity\n"
        "MOLASSES1000LITRE,ED&FMAN,10,320,2\n",
        encoding="utf-8",
    )

    rows = load_product_csv(path)

    assert rows["MOLASSES1000LITRE"]["supplier_code"] == "ED&FMAN"
    assert rows["MOLASSES1000LITRE"]["lead_time"] == "10"
    assert rows["MOLASSES1000LITRE"]["cost_price"] == "320"
    assert rows["MOLASSES1000LITRE"]["minimum_order_quantity"] == "2"

    path.write_text(
        "sku,supplier_code\nDUP-1,SUP1\ndup-1,SUP1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate SKU"):
        load_product_csv(path)


def test_apply_product_sync_uses_verified_csv_lead_time_cost_and_moq(db_session):
    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[{"id": 18, "code": "ED&FMAN", "name": "EDF Man", "is_active": True}],
        products=[{"id": 976, "sku": "MOLASSES1000LITRE", "name": "Organic Molasses", "is_active": True}],
        product_csv_rows={
            "MOLASSES1000LITRE": {
                "sku": "MOLASSES1000LITRE",
                "supplier_code": "ED&FMAN",
                "lead_time": "10",
                "cost_price": "320",
                "minimum_order_quantity": "2",
            }
        },
    )

    product = db_session.query(Product).filter_by(orderpro_sku="MOLASSES1000LITRE").one()
    assert report["products"]["summary"]["created"] == 1
    assert product.supplier_record.orderpro_code == "ED&FMAN"
    assert product.lead_time_days == 10
    assert product.cost_price == 320
    assert product.min_order_qty == 2


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


def test_product_planning_normalizes_supplier_codes_for_assignment(db_session):
    supplier = Supplier(
        name="Supplier One",
        normalized_name="supplier one",
        orderpro_id="10",
        orderpro_code="SUP1",
        source_system="orderpro",
    )
    product = Product(
        name="Existing Product",
        source_key="SKU-1",
        orderpro_id="1",
        orderpro_sku="SKU-1",
        supplier_id=None,
        source_system="orderpro",
    )
    db_session.add_all([supplier, product])
    db_session.flush()

    report = plan_product_sync(
        db_session,
        [{"id": 1, "sku": "SKU-1", "name": "Existing Product", "is_active": True}],
        {"sku-1": {"sku": "sku-1", "supplier_code": " sup1 ", "supplier_sku": "SUP-SKU-1"}},
        [{"id": 10, "code": "sup1", "name": "Supplier One"}],
    )

    assert report["summary"]["unknown_supplier_codes"] == 0
    assert report["summary"]["would_assign_supplier"] == 1
    assert report["would_assign_supplier"] == [
        {"sku": "SKU-1", "supplier_code": "SUP1", "local_supplier_id": supplier.id}
    ]
    assert report["to_update"][0]["changes"]["supplier_id"]["desired"] == supplier.id


def test_supplier_planning_matches_existing_supplier_by_normalized_code(db_session):
    supplier = Supplier(
        name="Supplier One",
        normalized_name="supplier one",
        orderpro_id="10",
        orderpro_code="SUP1",
        source_system="orderpro",
    )
    db_session.add(supplier)
    db_session.flush()

    report = plan_supplier_sync(
        db_session,
        [{"id": 10, "code": " sup1 ", "name": "Supplier One"}],
    )

    assert report["summary"]["already_matching"] == 1
    assert report["summary"]["to_create"] == 0
    assert report["already_matching"] == [{"local_id": supplier.id, "orderpro_id": "10", "orderpro_code": "SUP1"}]


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


def test_dry_run_inventory_performs_no_writes(db_session):
    product = Product(name="Product", orderpro_id="1", orderpro_sku="SKU-1")
    db_session.add(product)
    db_session.flush()

    report = plan_orderpro_sync(
        db_session,
        suppliers=[],
        products=[],
        product_csv_rows={},
        inventory=[
            {
                "id": "inv-1",
                "product_id": 1,
                "product": {"sku": "SKU-1"},
                "warehouse_id": "W1",
                "warehouse": {"name": "Main"},
                "qty": 5,
            }
        ],
    )

    assert report["inventory"]["summary"]["warehouses_to_create"] == 1
    assert db_session.query(Warehouse).count() == 0
    assert db_session.query(InventoryPosition).count() == 0
    assert product.current_stock == 0


def test_orderpro_order_dry_run_parses_headers_and_items(db_session):
    product = Product(name="Product", orderpro_id="100", orderpro_sku="SKU-100")
    db_session.add(product)
    db_session.flush()

    report = plan_order_sync(
        db_session,
        [
            {
                "id": 500,
                "order_number": "SO-500",
                "order_date": "2026-05-30T10:00:00Z",
                "status": "shipped",
                "source": "web",
                "items": [
                    {"id": 1, "product_id": 100, "sku": "SKU-100", "name": "Product", "qty_ordered": "2.000", "qty_shipped": "2.000", "unit_price": "5.0000", "line_total": "10.00"}
                ],
            }
        ],
    )

    assert report["summary"]["orderpro_orders"] == 1
    assert report["summary"]["orderpro_order_items"] == 1
    assert report["summary"]["orders_to_create"] == 1
    assert report["summary"]["order_items_to_create"] == 1
    assert report["summary"]["statuses_found"] == ["shipped"]
    assert report["summary"]["date_range"]["first_order_date"].startswith("2026-05-30T10:00:00")
    assert "product_id" in report["summary"]["sample_item_keys"]
    assert report["summary"]["positive_qty_ordered_count"] == 1
    assert report["summary"]["positive_qty_shipped_count"] == 1
    assert report["summary"]["total_qty_ordered"] == 2
    assert report["summary"]["total_qty_shipped"] == 2


def test_orderpro_order_item_matches_product_by_orderpro_id_and_sku_fallback(db_session):
    product_by_id = Product(name="By ID", orderpro_id="100", orderpro_sku="SKU-100")
    product_by_sku = Product(name="By SKU", orderpro_id="101", orderpro_sku="SKU-101")
    db_session.add_all([product_by_id, product_by_sku])
    db_session.flush()

    report = plan_order_sync(
        db_session,
        [
            {
                "id": 501,
                "order_number": "SO-501",
                "items": [
                    {"id": "line-1", "product_id": 100, "qty_ordered": "1.000", "qty_shipped": "1.000"},
                    {"id": "line-2", "product": {"sku": "SKU-101"}, "qty_ordered": "3.000", "qty_shipped": "3.000"},
                ],
            }
        ],
    )

    planned_by_key = {row["orderpro_id"]: row for row in report["order_items_to_create"]}
    assert planned_by_key["line-1"]["product_id"] == product_by_id.id
    assert planned_by_key["line-2"]["product_id"] == product_by_sku.id
    assert report["summary"]["items_missing_product_match"] == 0


def test_orderpro_order_item_sku_fallback_is_normalized(db_session):
    product_by_sku = Product(name="By SKU", orderpro_id="101", orderpro_sku="SKU-101")
    db_session.add(product_by_sku)
    db_session.flush()

    report = plan_order_sync(
        db_session,
        [
            {
                "id": 501,
                "order_number": "SO-501",
                "items": [
                    {"id": "line-1", "product": {"sku": " sku-101 "}, "qty_ordered": "3.000", "qty_shipped": "3.000"},
                ],
            }
        ],
    )

    assert report["order_items_to_create"][0]["product_id"] == product_by_sku.id
    assert report["summary"]["items_missing_product_match"] == 0


def test_orderpro_inventory_planning_sku_fallback_is_normalized(db_session):
    product = Product(name="Product", source_key="SKU-1", orderpro_id="1", orderpro_sku="SKU-1")
    warehouse = Warehouse(orderpro_id="W1", name="Main Warehouse", source_system="orderpro")
    db_session.add_all([product, warehouse])
    db_session.flush()

    report = plan_inventory_sync(
        db_session,
        [
            {
                "product_id": 999,
                "product": {"sku": " sku-1 "},
                "warehouse_id": "W1",
                "location_id": "L1",
                "qty": 5,
            },
        ],
    )

    assert report["summary"]["rows_missing_product_match"] == 0
    assert report["inventory_positions_to_create"][0]["product_id"] == product.id
    assert report["total_stock_by_local_product_id"][str(product.id)] == 5


def test_orderpro_order_dry_run_reports_missing_product_match(db_session):
    report = plan_order_sync(
        db_session,
        [{"id": 502, "order_number": "SO-502", "items": [{"id": "line-1", "sku": "UNKNOWN", "qty_ordered": "1.000", "qty_shipped": "1.000"}]}],
    )

    assert report["summary"]["items_missing_product_match"] == 1
    assert report["items_missing_product_match_sample"] == [
        {
            "orderpro_order_id": "502",
            "order_number": "SO-502",
            "orderpro_product_id": None,
            "sku": "UNKNOWN",
            "name": None,
        }
    ]


def test_orderpro_order_dry_run_performs_no_writes(db_session):
    report = plan_orderpro_sync(
        db_session,
        suppliers=[],
        products=[],
        product_csv_rows={},
        inventory=None,
        orders=[{"id": 503, "order_number": "SO-503", "items": [{"sku": "UNKNOWN", "qty_ordered": "1.000", "qty_shipped": "1.000"}]}],
    )

    assert report["orders"]["summary"]["orders_to_create"] == 1
    assert db_session.query(OrderProOrder).count() == 0
    assert db_session.query(OrderProOrderItem).count() == 0


def test_orderpro_order_dry_run_reports_quantity_statistics_and_invalid_samples(db_session):
    report = plan_order_sync(
        db_session,
        [
            {
                "id": 504,
                "order_number": "SO-504",
                "items": [
                    {"id": "valid", "sku": "SKU-1", "qty_ordered": "3.500", "qty_picked": "2.000", "qty_shipped": "1.250"},
                    {"id": "missing", "sku": "SKU-2"},
                    {"id": "invalid", "sku": "SKU-3", "qty_ordered": "not-a-number", "qty_shipped": "0.000"},
                    {"id": "negative", "sku": "SKU-4", "qty_ordered": "-2.000", "qty_shipped": "-1.000"},
                ],
            }
        ],
    )

    assert report["summary"]["order_item_total_count"] == 4
    assert report["summary"]["positive_qty_ordered_count"] == 1
    assert report["summary"]["positive_qty_shipped_count"] == 1
    assert report["summary"]["zero_qty_shipped_count"] == 1
    assert report["summary"]["missing_or_invalid_quantity_count"] == 2
    assert report["summary"]["total_qty_ordered"] == 1.5
    assert report["summary"]["total_qty_shipped"] == 0.25
    assert report["summary"]["total_calculated_open_quantity"] == 2.25
    assert report["quantity_source_field_counts"] == {
        "qty_ordered": 3,
        "qty_picked": 1,
        "qty_shipped": 3,
        "legacy_quantity": 0,
        "legacy_qty": 0,
    }
    assert {sample["sku"] for sample in report["invalid_quantity_samples"]} == {"SKU-2", "SKU-3"}


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
        "https://wms.orderpro.cloud/api/v2/products?page=1&per_page=200",
        "https://wms.orderpro.cloud/api/v2/products?page=2&per_page=200",
    ]


def test_fetch_orderpro_records_fetches_all_pages_when_no_limit():
    seen_params = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        seen_params.append((page, request.url.params.get("per_page")))
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
    assert seen_params == [(1, "200"), (2, "200")]


def test_fetch_orderpro_records_status_reports_limit_only_when_truncated():
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(
            200,
            json={"data": [{"id": page}], "meta": {"current_page": page, "last_page": 2}},
        )

    client = OrderProClient(
        base_url="https://wms.orderpro.cloud/api/v2",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    complete = fetch_orderpro_records_with_status(client, "/suppliers", limit_pages=2)
    truncated = fetch_orderpro_records_with_status(client, "/suppliers", limit_pages=1)

    assert complete.pages_fetched == 2
    assert complete.truncated_by_limit is False
    assert truncated.pages_fetched == 1
    assert truncated.truncated_by_limit is True


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


def test_apply_creates_suppliers_and_products_with_csv_supplier_assignment(db_session):
    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[{"id": 10, "code": "SUP1", "name": "Supplier One", "email": "one@example.test", "phone": "111", "is_active": True}],
        products=[
            {
                "id": 100,
                "sku": "SKU-100",
                "name": "Product One",
                "description": "A product",
                "cost_price": "4.5",
                "sell_price": "6.5",
                "is_active": True,
            }
        ],
        product_csv_rows={"SKU-100": {"sku": "SKU-100", "supplier_code": "SUP1", "supplier_sku": "SUP-SKU-100"}},
    )

    supplier = db_session.query(Supplier).filter_by(orderpro_code="SUP1").one()
    product = db_session.query(Product).filter_by(orderpro_sku="SKU-100").one()

    assert report["mode"] == "apply"
    assert report["suppliers"]["summary"]["created"] == 1
    assert report["products"]["summary"]["created"] == 1
    assert supplier.orderpro_id == "10"
    assert supplier.source_system == "orderpro"
    assert supplier.last_synced_at is not None
    assert product.orderpro_id == "100"
    assert product.source_system == "orderpro"
    assert product.supplier_id == supplier.id
    assert product.supplier_sku == "SUP-SKU-100"
    assert product.cost_price == 4.5
    assert product.last_synced_at is not None


def test_apply_creates_product_with_long_description_preserved(db_session):
    long_description = "Smooth Operator Fluffer Comb " + ("very long description " * 80)

    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[],
        products=[
            {
                "id": 600,
                "sku": "6FLUFFERCOMB",
                "name": "6' Smooth Operator Fluffer Comb",
                "description": long_description,
                "is_active": True,
            }
        ],
        product_csv_rows={"6FLUFFERCOMB": {"sku": "6FLUFFERCOMB", "supplier_code": "", "supplier_sku": ""}},
    )

    product = db_session.query(Product).filter_by(orderpro_sku="6FLUFFERCOMB").one()

    assert report["products"]["summary"]["created"] == 1
    assert report["products"]["summary"]["field_limit_violations"] == 0
    assert product.description == long_description
    assert len(product.description) > 1000


def test_apply_skips_product_with_remaining_column_limit_violation(db_session):
    too_long_name = "N" * 300

    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[],
        products=[{"id": 700, "sku": "LONG-NAME", "name": too_long_name, "is_active": True}],
        product_csv_rows={"LONG-NAME": {"sku": "LONG-NAME", "supplier_code": "", "supplier_sku": ""}},
    )

    assert report["products"]["summary"]["created"] == 0
    assert report["products"]["summary"]["field_limit_violations"] == 1
    assert report["products"]["field_limit_violations"][0]["field"] == "name"
    assert db_session.query(Product).filter_by(orderpro_sku="LONG-NAME").count() == 0


def test_apply_links_existing_supplier_by_name_without_duplicate_or_overwriting_local_fields(db_session):
    local = Supplier(
        name="Acravet Ltd",
        normalized_name="acravet ltd",
        notes="Important local note",
        lead_time_days=21,
        payment_terms="Net 30",
    )
    db_session.add(local)
    db_session.flush()

    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[{"id": 55, "code": "ACR", "name": "Acravet Ltd", "email": "sales@example.test", "phone": "555", "is_active": True}],
        products=[{"id": 100, "sku": "SKU-100", "name": "Product One", "is_active": True}],
        product_csv_rows={"SKU-100": {"sku": "SKU-100", "supplier_code": "ACR", "supplier_sku": "SUP-SKU-100"}},
    )

    db_session.refresh(local)
    product = db_session.query(Product).filter_by(orderpro_sku="SKU-100").one()

    assert report["suppliers"]["summary"]["created"] == 0
    assert report["suppliers"]["summary"]["updated"] == 1
    assert report["suppliers"]["summary"]["linked_existing_by_name"] == 1
    assert db_session.query(Supplier).count() == 1
    assert local.orderpro_id == "55"
    assert local.orderpro_code == "ACR"
    assert local.source_system == "orderpro"
    assert local.email == "sales@example.test"
    assert local.notes == "Important local note"
    assert local.lead_time_days == 21
    assert local.payment_terms == "Net 30"
    assert product.supplier_id == local.id


def test_apply_supplier_matching_still_uses_orderpro_id_before_name(db_session):
    supplier_by_id = Supplier(
        name="Different Local Name",
        normalized_name="different local name",
        orderpro_id="55",
    )
    same_name_other_supplier = Supplier(
        name="OrderPro Name",
        normalized_name="orderpro name",
    )
    db_session.add_all([supplier_by_id, same_name_other_supplier])
    db_session.flush()

    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[{"id": 55, "code": "ACR", "name": "OrderPro Name", "email": "sales@example.test"}],
        products=[],
        product_csv_rows={},
    )

    db_session.refresh(supplier_by_id)
    db_session.refresh(same_name_other_supplier)

    assert report["suppliers"]["summary"]["created"] == 0
    assert report["suppliers"]["summary"]["updated"] == 1
    assert supplier_by_id.orderpro_code == "ACR"
    assert supplier_by_id.name == "Different Local Name"
    assert same_name_other_supplier.orderpro_code is None


def test_apply_supplier_matching_still_uses_orderpro_code(db_session):
    supplier = Supplier(
        name="Existing Code Supplier",
        normalized_name="existing code supplier",
        orderpro_code="SUP1",
    )
    db_session.add(supplier)
    db_session.flush()

    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[{"id": 10, "code": "SUP1", "name": "Existing Code Supplier", "phone": "111"}],
        products=[],
        product_csv_rows={},
    )

    db_session.refresh(supplier)

    assert report["suppliers"]["summary"]["created"] == 0
    assert supplier.orderpro_id == "10"
    assert supplier.phone == "111"


def test_apply_creates_supplier_only_when_id_code_and_name_do_not_match(db_session):
    existing = Supplier(name="Existing Supplier", normalized_name="existing supplier")
    db_session.add(existing)
    db_session.flush()

    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[{"id": 10, "code": "SUP1", "name": "New Supplier"}],
        products=[],
        product_csv_rows={},
    )

    assert report["suppliers"]["summary"]["created"] == 1
    assert db_session.query(Supplier).count() == 2


def test_apply_updates_existing_suppliers_and_products(db_session):
    supplier = Supplier(
        name="Old Supplier",
        normalized_name="old supplier",
        orderpro_id="10",
        orderpro_code="SUP1",
        email="old@example.test",
    )
    product = Product(
        name="Old Product",
        source_key="SKU-100",
        orderpro_id="100",
        orderpro_sku="SKU-100",
        source_system="local",
        supplier_sku="OLD-SKU",
    )
    db_session.add_all([supplier, product])
    db_session.flush()

    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[{"id": 10, "code": "SUP1", "name": "New Supplier", "email": "new@example.test", "phone": "222", "is_active": False}],
        products=[{"id": 100, "sku": "SKU-100", "name": "New Product", "brand": "Brand", "is_active": True}],
        product_csv_rows={"SKU-100": {"sku": "SKU-100", "supplier_code": "SUP1", "supplier_sku": "NEW-SKU"}},
    )

    db_session.refresh(supplier)
    db_session.refresh(product)

    assert report["suppliers"]["summary"]["updated"] == 1
    assert report["products"]["summary"]["updated"] == 1
    assert supplier.name == "New Supplier"
    assert supplier.normalized_name == "new supplier"
    assert supplier.email == "new@example.test"
    assert supplier.is_active is False
    assert product.name == "New Product"
    assert product.brand == "Brand"
    assert product.source_system == "orderpro"
    assert product.supplier_id == supplier.id
    assert product.supplier_sku == "NEW-SKU"


def test_apply_missing_supplier_code_leaves_product_supplier_id_null_and_reports_warning(db_session):
    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[{"id": 10, "code": "SUP1", "name": "Supplier One"}],
        products=[{"id": 100, "sku": "SKU-100", "name": "Product One", "is_active": True}],
        product_csv_rows={"SKU-100": {"sku": "SKU-100", "supplier_code": "", "supplier_sku": ""}},
    )

    product = db_session.query(Product).filter_by(orderpro_sku="SKU-100").one()

    assert product.supplier_id is None
    assert report["products"]["summary"]["csv_rows_missing_supplier_code"] == 1
    assert "missing supplier_code" in " ".join(report["products"]["warnings"])


def test_apply_unknown_supplier_code_reports_without_creating_fake_supplier(db_session):
    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[{"id": 10, "code": "SUP1", "name": "Supplier One"}],
        products=[{"id": 100, "sku": "SKU-100", "name": "Product One", "is_active": True}],
        product_csv_rows={"SKU-100": {"sku": "SKU-100", "supplier_code": "UNKNOWN", "supplier_sku": "SUP-SKU"}},
    )

    product = db_session.query(Product).filter_by(orderpro_sku="SKU-100").one()

    assert product.supplier_id is None
    assert db_session.query(Supplier).count() == 1
    assert report["products"]["summary"]["unknown_supplier_codes"] == 1
    assert report["products"]["unknown_supplier_codes"] == [{"sku": "SKU-100", "supplier_code": "UNKNOWN"}]


def test_apply_does_not_deactivate_missing_local_products_by_default(db_session):
    existing = Product(
        name="Existing",
        source_key="OLD-SKU",
        orderpro_id="999",
        orderpro_sku="OLD-SKU",
        source_system="orderpro",
        is_active=True,
    )
    db_session.add(existing)
    db_session.flush()

    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[],
        products=[],
        product_csv_rows={},
    )

    db_session.refresh(existing)

    assert existing.is_active is True
    assert report["products"]["summary"]["deactivated_missing_orderpro_products"] == 0
    assert report["products"]["summary"]["mark_missing_inactive"] is False


def test_apply_mark_missing_inactive_is_required_before_deactivation(db_session):
    existing = Product(
        name="Existing",
        source_key="OLD-SKU",
        orderpro_id="999",
        orderpro_sku="OLD-SKU",
        source_system="orderpro",
        is_active=True,
    )
    db_session.add(existing)
    db_session.flush()

    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[],
        products=[],
        product_csv_rows={},
        mark_missing_inactive=True,
    )

    db_session.refresh(existing)

    assert existing.is_active is False
    assert report["products"]["summary"]["deactivated_missing_orderpro_products"] == 1
    assert report["products"]["summary"]["mark_missing_inactive"] is True


def test_apply_inventory_creates_derived_warehouse_position_and_updates_stock_by_orderpro_id(db_session):
    product = Product(name="Product", orderpro_id="1", orderpro_sku="SKU-1", current_stock=0)
    db_session.add(product)
    db_session.flush()

    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[],
        products=[],
        product_csv_rows={},
        inventory=[
            {
                "id": "inv-1",
                "product_id": 1,
                "product": {"sku": "SKU-1"},
                "warehouse_id": "W1",
                "warehouse": {"name": "Main Warehouse", "code": "MAIN"},
                "location_id": "L1",
                "location": {"name": "Aisle 1"},
                "lot_id": "LOT1",
                "lot": "Lot 1",
                "qty": 7,
            }
        ],
    )

    warehouse = db_session.query(Warehouse).filter_by(orderpro_id="W1").one()
    position = db_session.query(InventoryPosition).one()
    db_session.refresh(product)

    assert report["inventory"]["summary"]["warehouses_created"] == 1
    assert report["inventory"]["summary"]["inventory_positions_created"] == 1
    assert report["inventory"]["summary"]["products_current_stock_updated"] == 1
    assert warehouse.name == "Main Warehouse"
    assert warehouse.code == "MAIN"
    assert warehouse.last_synced_at is not None
    assert position.product_id == product.id
    assert position.warehouse_id == warehouse.id
    assert position.orderpro_inventory_id == "inv-1"
    assert position.orderpro_product_id == "1"
    assert position.orderpro_warehouse_id == "W1"
    assert position.location_id == "L1"
    assert position.location_name == "Aisle 1"
    assert position.lot_id == "LOT1"
    assert position.lot == "Lot 1"
    assert position.quantity_on_hand == 7
    assert product.current_stock == 7


def test_apply_inventory_updates_existing_warehouse_and_position(db_session):
    product = Product(name="Product", orderpro_id="1", orderpro_sku="SKU-1", current_stock=2)
    warehouse = Warehouse(orderpro_id="W1", name="Old Warehouse", code="OLD")
    db_session.add_all([product, warehouse])
    db_session.flush()
    position = InventoryPosition(
        product_id=product.id,
        warehouse_id=warehouse.id,
        orderpro_inventory_id="old-inv",
        orderpro_product_id="1",
        orderpro_warehouse_id="W1",
        location_id="L1",
        quantity_on_hand=2,
        on_hand=2,
        available=2,
    )
    db_session.add(position)
    db_session.flush()

    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[],
        products=[],
        product_csv_rows={},
        inventory=[
            {
                "id": "inv-1",
                "product_id": 1,
                "product": {"sku": "SKU-1"},
                "warehouse_id": "W1",
                "warehouse": {"name": "New Warehouse", "code": "NEW"},
                "location_id": "L1",
                "qty": 9,
            }
        ],
    )

    db_session.refresh(warehouse)
    db_session.refresh(position)
    db_session.refresh(product)

    assert report["inventory"]["summary"]["warehouses_updated"] == 1
    assert report["inventory"]["summary"]["inventory_positions_updated"] == 1
    assert warehouse.name == "New Warehouse"
    assert warehouse.code == "NEW"
    assert position.orderpro_inventory_id == "inv-1"
    assert position.quantity_on_hand == 9
    assert product.current_stock == 9


def test_apply_inventory_matches_product_by_nested_sku_fallback(db_session):
    product = Product(name="Product", orderpro_id="1", orderpro_sku="SKU-1")
    db_session.add(product)
    db_session.flush()

    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[],
        products=[],
        product_csv_rows={},
        inventory=[
            {
                "id": "inv-1",
                "product": {"sku": "SKU-1"},
                "warehouse_id": "W1",
                "warehouse": "Main Warehouse",
                "qty": 4,
            }
        ],
    )

    position = db_session.query(InventoryPosition).one()
    db_session.refresh(product)

    assert report["inventory"]["summary"]["inventory_positions_created"] == 1
    assert position.product_id == product.id
    assert product.current_stock == 4


def test_apply_inventory_reports_and_skips_missing_product_or_warehouse(db_session):
    product = Product(name="Product", orderpro_id="1", orderpro_sku="SKU-1")
    db_session.add(product)
    db_session.flush()

    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[],
        products=[],
        product_csv_rows={},
        inventory=[
            {"id": "inv-1", "product_id": 999, "product": {"sku": "NOPE"}, "warehouse_id": "W1", "qty": 5},
            {"id": "inv-2", "product_id": 1, "product": {"sku": "SKU-1"}, "qty": 3},
        ],
    )

    assert report["inventory"]["summary"]["rows_missing_product_match"] == 1
    assert report["inventory"]["summary"]["rows_missing_warehouse_id"] == 1
    assert report["inventory"]["summary"]["inventory_positions_created"] == 0
    assert db_session.query(InventoryPosition).count() == 0


def test_apply_inventory_updates_current_stock_as_total_across_warehouses(db_session):
    product = Product(name="Product", orderpro_id="1", orderpro_sku="SKU-1", current_stock=0)
    db_session.add(product)
    db_session.flush()

    apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[],
        products=[],
        product_csv_rows={},
        inventory=[
            {"id": "inv-1", "product_id": 1, "product": {"sku": "SKU-1"}, "warehouse_id": "W1", "warehouse": "Main", "qty": 4},
            {"id": "inv-2", "product_id": 1, "product": {"sku": "SKU-1"}, "warehouse_id": "W2", "warehouse": "Remote", "qty": 6},
        ],
    )

    db_session.refresh(product)

    assert product.current_stock == 10


def test_apply_orderpro_orders_creates_headers_and_items(db_session):
    product = Product(name="Product", orderpro_id="100", orderpro_sku="SKU-100")
    db_session.add(product)
    db_session.flush()

    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[],
        products=[],
        product_csv_rows={},
        orders=[
            {
                "id": 900,
                "order_number": "SO-900",
                "order_date": "2026-05-31T09:00:00Z",
                "status": "complete",
                "source": "web",
                "customer_name": "Customer One",
                "warehouse_id": "W1",
                "subtotal": "10.0",
                "tax_amount": "2.0",
                "shipping_cost": "1.5",
                "total_amount": "13.5",
                "currency": "GBP",
                "items": [
                    {
                        "id": "line-1",
                        "product_id": 100,
                        "sku": "SKU-100",
                        "name": "Product",
                        "qty_ordered": "2.500",
                        "qty_picked": "2.000",
                        "qty_shipped": "2.000",
                        "unit_price": "5.2500",
                        "line_total": "10.50",
                    }
                ],
            }
        ],
    )

    order = db_session.query(OrderProOrder).filter_by(orderpro_id="900").one()
    item = db_session.query(OrderProOrderItem).one()

    assert report["orders"]["summary"]["orders_created"] == 1
    assert report["orders"]["summary"]["order_items_created"] == 1
    assert order.order_number == "SO-900"
    assert order.status == "complete"
    assert order.orderpro_warehouse_id == "W1"
    assert order.total_amount == 13.5
    assert order.raw_snapshot["order_number"] == "SO-900"
    assert item.order_id == order.id
    assert item.product_id == product.id
    assert item.orderpro_product_id == "100"
    assert item.sku == "SKU-100"
    assert item.quantity == 2
    assert item.quantity_ordered == 2.5
    assert item.quantity_picked == 2
    assert item.quantity_shipped == 2
    assert item.unit_price == 5.25
    assert item.total == 10.5


def test_orderpro_order_item_quantity_parser_preserves_explicit_orderpro_quantities():
    desired = desired_order_item_fields(
        {"id": 900, "status": "shipped"},
        {
            "id": "line-1",
            "product_id": 100,
            "sku": "SKU-100",
            "qty_ordered": "3.500",
            "qty_picked": "2.250",
            "qty_shipped": "1.750",
            "unit_price": "19.0000",
            "line_total": "33.25",
        },
        index=1,
        product_id=10,
    )

    assert desired["quantity_ordered"] == 3.5
    assert desired["quantity_picked"] == 2.25
    assert desired["quantity_shipped"] == 1.75
    assert desired["quantity"] == 1.75
    assert desired["unit_price"] == 19
    assert desired["total"] == 33.25


def test_orderpro_order_item_quantity_parser_uses_ordered_when_shipped_missing():
    desired = desired_order_item_fields(
        {"id": 901, "status": "confirmed"},
        {
            "id": "line-1",
            "product_id": 100,
            "sku": "SKU-100",
            "qty_ordered": "4.000",
            "qty_picked": "0.000",
        },
        index=1,
        product_id=10,
    )

    assert desired["quantity_ordered"] == 4
    assert desired["quantity_picked"] == 0
    assert desired["quantity_shipped"] is None
    assert desired["quantity"] == 4


def test_orderpro_order_quantity_diagnostics_reports_missing_invalid_negative_and_open_quantities():
    report = order_quantity_diagnostics(
        [
            {
                "id": 900,
                "order_number": "SO-900",
                "items": [
                    {"id": "line-1", "sku": "VALID", "qty_ordered": "3.500", "qty_shipped": "1.000"},
                    {"id": "line-2", "sku": "MISSING"},
                    {"id": "line-3", "sku": "INVALID", "qty_ordered": "not-a-number", "qty_shipped": "0.000"},
                    {"id": "line-4", "sku": "RETURN", "qty_ordered": "-2.000", "qty_shipped": "-1.000"},
                ],
            }
        ]
    )

    assert report["summary"]["order_item_total_count"] == 4
    assert report["summary"]["positive_qty_ordered_count"] == 1
    assert report["summary"]["positive_qty_shipped_count"] == 1
    assert report["summary"]["zero_qty_shipped_count"] == 1
    assert report["summary"]["missing_or_invalid_quantity_count"] == 2
    assert report["summary"]["total_qty_ordered"] == 1.5
    assert report["summary"]["total_qty_shipped"] == 0
    assert report["summary"]["total_calculated_open_quantity"] == 2.5
    assert report["quantity_source_field_counts"]["qty_ordered"] == 3
    assert report["quantity_source_field_counts"]["qty_shipped"] == 3
    assert {sample["reason"] for sample in report["invalid_quantity_samples"]} == {
        "missing_qty_ordered_and_qty_shipped",
        "invalid_quantity",
    }


def test_apply_orderpro_orders_updates_instead_of_duplicating(db_session):
    product = Product(name="Product", orderpro_id="100", orderpro_sku="SKU-100")
    db_session.add(product)
    db_session.flush()

    first_payload = {
        "id": 901,
        "order_number": "SO-901",
        "status": "new",
        "items": [{"id": "line-1", "product_id": 100, "sku": "SKU-100", "qty_ordered": "1.000", "qty_shipped": "1.000", "unit_price": "5.0000"}],
    }
    apply_orderpro_supplier_product_sync(db_session, suppliers=[], products=[], product_csv_rows={}, orders=[first_payload])
    second_payload = {
        "id": 901,
        "order_number": "SO-901",
        "status": "shipped",
        "items": [{"id": "line-1", "product_id": 100, "sku": "SKU-100", "qty_ordered": "3.000", "qty_shipped": "3.000", "unit_price": "4.0000"}],
    }
    report = apply_orderpro_supplier_product_sync(db_session, suppliers=[], products=[], product_csv_rows={}, orders=[second_payload])

    order = db_session.query(OrderProOrder).filter_by(orderpro_id="901").one()
    item = db_session.query(OrderProOrderItem).one()

    assert report["orders"]["summary"]["orders_updated"] == 1
    assert report["orders"]["summary"]["order_items_updated"] == 1
    assert db_session.query(OrderProOrder).count() == 1
    assert db_session.query(OrderProOrderItem).count() == 1
    assert order.status == "shipped"
    assert item.quantity == 3
    assert item.quantity_ordered == 3
    assert item.quantity_shipped == 3
    assert item.unit_price == 4


def test_apply_orderpro_orders_repairs_existing_zero_quantity_item(db_session):
    product = Product(name="Product", orderpro_id="100", orderpro_sku="SKU-100")
    order = OrderProOrder(orderpro_id="903", order_number="SO-903", status="shipped")
    db_session.add_all([product, order])
    db_session.flush()
    db_session.add(
        OrderProOrderItem(
            order=order,
            product=product,
            orderpro_id="line-1",
            orderpro_line_key="line-1",
            orderpro_product_id="100",
            sku="SKU-100",
            quantity=0,
        )
    )
    db_session.flush()

    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[],
        products=[],
        product_csv_rows={},
        orders=[
            {
                "id": 903,
                "order_number": "SO-903",
                "status": "shipped",
                "items": [
                    {
                        "id": "line-1",
                        "product_id": 100,
                        "sku": "SKU-100",
                        "qty_ordered": "3.000",
                        "qty_picked": "3.000",
                        "qty_shipped": "3.000",
                        "unit_price": "19.0000",
                        "line_total": "57.00",
                    }
                ],
            }
        ],
    )

    item = db_session.query(OrderProOrderItem).one()

    assert report["orders"]["summary"]["order_items_updated"] == 1
    assert db_session.query(OrderProOrderItem).count() == 1
    assert item.quantity == 3
    assert item.quantity_ordered == 3
    assert item.quantity_picked == 3
    assert item.quantity_shipped == 3
    assert item.unit_price == 19
    assert item.total == 57


def test_orderpro_order_snapshots_do_not_store_tokens(db_session):
    report = apply_orderpro_supplier_product_sync(
        db_session,
        suppliers=[],
        products=[],
        product_csv_rows={},
        orders=[
            {
                "id": 902,
                "order_number": "SO-902",
                "api_token": "secret-token",
                "items": [{"id": "line-1", "sku": "UNKNOWN", "qty_ordered": "1.000", "qty_shipped": "1.000", "authorization": "Bearer secret-token"}],
            }
        ],
    )

    order = db_session.query(OrderProOrder).filter_by(orderpro_id="902").one()
    item = db_session.query(OrderProOrderItem).one()

    assert "secret-token" not in str(report)
    assert "api_token" not in order.raw_snapshot
    assert "authorization" not in item.raw_snapshot
