from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier


def test_product_can_have_multiple_supplier_mappings(db_session):
    product = Product(name="Widget", current_stock=10)
    supplier_a = Supplier(name="Supplier A", normalized_name="SUPPLIER A")
    supplier_b = Supplier(name="Supplier B", normalized_name="SUPPLIER B")
    db_session.add_all([product, supplier_a, supplier_b])
    db_session.flush()

    mapping_a = ProductSupplier(
        product_id=product.id,
        supplier_id=supplier_a.id,
        supplier_sku="SKU-A",
        supplier_product_name="Widget A",
        purchase_price=10.5,
        match_status="matched",
        match_method="exact_sku",
    )
    mapping_b = ProductSupplier(
        product_id=product.id,
        supplier_id=supplier_b.id,
        supplier_sku="SKU-B",
        supplier_product_name="Widget B",
        purchase_price=11.25,
        match_status="matched",
        match_method="exact_name",
    )
    db_session.add_all([mapping_a, mapping_b])
    db_session.commit()

    db_session.refresh(product)

    assert len(product.product_suppliers) == 2
    assert {mapping.supplier_sku for mapping in product.product_suppliers} == {"SKU-A", "SKU-B"}
    assert mapping_a.is_preferred is False
    assert mapping_a.supplier_product_name == "Widget A"
    assert mapping_a.purchase_price == 10.5
    assert mapping_a.match_status == "matched"
    assert mapping_a.match_method == "exact_sku"
    assert mapping_a.supplier.name == "Supplier A"


def test_supplier_can_map_to_multiple_products(db_session):
    supplier = Supplier(name="Supplier A", normalized_name="SUPPLIER A")
    product_a = Product(name="Widget A", current_stock=1)
    product_b = Product(name="Widget B", current_stock=2)
    db_session.add_all([supplier, product_a, product_b])
    db_session.flush()

    db_session.add_all(
        [
            ProductSupplier(product_id=product_a.id, supplier_id=supplier.id, supplier_sku="A-1"),
            ProductSupplier(product_id=product_b.id, supplier_id=supplier.id, supplier_sku="B-1"),
        ]
    )
    db_session.commit()
    db_session.refresh(supplier)

    assert len(supplier.product_suppliers) == 2
    assert {mapping.product.name for mapping in supplier.product_suppliers} == {"Widget A", "Widget B"}
