from sqlalchemy.orm import selectinload

from app.models.product import Product
from app.models.supplier import Supplier
from app.services.forecasting import resolve_supplier_context


def seed_supplier(db_session) -> Supplier:
    supplier = Supplier(
        name="ED&F Man",
        normalized_name="ed&f man",
        orderpro_id="18",
        orderpro_code="ED&FMAN",
        source_system="orderpro",
        email="sales@example.test",
        lead_time_needs_review=True,
    )
    db_session.add(supplier)
    db_session.flush()
    db_session.add_all(
        [
            Product(
                name="Organic Molasses - 1000 Litre",
                orderpro_id="976",
                orderpro_sku="MOLASSES1000LITRE",
                supplier_id=supplier.id,
                current_stock=0,
                lead_time_days=0,
                is_active=True,
            ),
            Product(
                name="Organic Molasses 1000 Litres",
                orderpro_id="977",
                orderpro_sku="ORGANICMOLASSES1000LITRES",
                supplier_id=supplier.id,
                current_stock=0,
                lead_time_days=0,
                is_active=False,
            ),
        ]
    )
    db_session.commit()
    return supplier


def test_supplier_list_returns_management_fields_and_product_counts(client, db_session):
    supplier = seed_supplier(db_session)

    response = client.get("/suppliers")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": supplier.id,
            "name": "ED&F Man",
            "orderpro_id": "18",
            "orderpro_code": "ED&FMAN",
            "source_system": "orderpro",
            "is_active": True,
            "local_profile_override": False,
            "last_synced_at": None,
            "email": "sales@example.test",
            "phone": None,
            "website": None,
            "contact_method": None,
            "payment_terms": None,
            "lead_time_raw": None,
            "lead_time_days": None,
            "lead_time_min_days": None,
            "lead_time_max_days": None,
            "notes": None,
            "active_skus": 0,
            "lead_time_needs_review": True,
            "product_count": 2,
            "active_product_count": 1,
            "writes_to_orderpro": False,
        }
    ]


def test_supplier_detail_returns_404_for_unknown_supplier(client):
    response = client.get("/suppliers/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Supplier not found."


def test_supplier_patch_saves_local_business_data(client, db_session):
    supplier = seed_supplier(db_session)

    response = client.patch(
        f"/suppliers/{supplier.id}",
        json={
            "email": "  purchasing@edfman.test ",
            "phone": "+44 20 5555 0100",
            "website": "https://edfman.example.test",
            "contact_method": "Email",
            "payment_terms": "Net 30",
            "lead_time_days": 10,
            "lead_time_min_days": 8,
            "lead_time_max_days": 14,
            "notes": "Confirm IBC availability before ordering.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "purchasing@edfman.test"
    assert body["lead_time_days"] == 10
    assert body["lead_time_raw"] == "10 days"
    assert body["lead_time_needs_review"] is False
    assert body["local_profile_override"] is True
    assert body["writes_to_orderpro"] is False

    db_session.expire_all()
    saved = db_session.get(Supplier, supplier.id)
    assert saved.payment_terms == "Net 30"
    assert saved.notes == "Confirm IBC availability before ordering."


def test_supplier_patch_rejects_inconsistent_lead_time_range(client, db_session):
    supplier = seed_supplier(db_session)

    response = client.patch(
        f"/suppliers/{supplier.id}",
        json={"lead_time_days": 10, "lead_time_min_days": 15, "lead_time_max_days": 20},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Lead time cannot be below the minimum lead time."


def test_supplier_lead_time_update_is_used_by_linked_product_forecast(client, db_session):
    supplier = seed_supplier(db_session)

    response = client.patch(f"/suppliers/{supplier.id}", json={"lead_time_days": 10})
    assert response.status_code == 200

    db_session.expire_all()
    product = (
        db_session.query(Product)
        .options(selectinload(Product.supplier_record))
        .filter(Product.orderpro_sku == "MOLASSES1000LITRE")
        .one()
    )
    context = resolve_supplier_context(product)

    assert context["lead_time_days_used"] == 10
    assert context["lead_time_source"] == "supplier_record"


def test_supplier_forecast_includes_supplier_level_stock_warning_summary(client, db_session):
    supplier = seed_supplier(db_session)
    active_product = (
        db_session.query(Product)
        .filter(Product.supplier_id == supplier.id, Product.is_active.is_(True))
        .one()
    )

    response = client.get(f"/suppliers/{supplier.id}/forecast")

    assert response.status_code == 200
    body = response.json()
    assert body["supplier_code"] == "ED&FMAN"
    assert body["total_current_stock"] == 0
    assert body["out_of_stock_products"] == [active_product.id]
    assert body["products_missing_data"] == [active_product.id]
    assert body["stock_status"] == "watch"
    assert body["inventory_last_synced_at"] is None
