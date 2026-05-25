from sqlalchemy import and_, func

import app.models  # noqa: F401
from app.db.session import SessionLocal
from app.models.product_master_item import ProductMasterItem
from app.models.product_supplier import ProductSupplier


SAMPLE_LIMIT = 10


def print_section(title: str) -> None:
    print()
    print("=" * len(title))
    print(title)
    print("=" * len(title))


def print_count(label: str, value: int) -> None:
    print(f"{label}: {value}")


def print_rows(rows) -> None:
    if not rows:
        print("(none)")
        return

    for row in rows:
        print(row)


def main() -> None:
    db = SessionLocal()

    try:
        total_master_items = db.query(func.count(ProductMasterItem.id)).scalar() or 0
        with_product_and_supplier = (
            db.query(func.count(ProductMasterItem.id))
            .filter(
                ProductMasterItem.product_id.is_not(None),
                ProductMasterItem.supplier_id.is_not(None),
            )
            .scalar()
            or 0
        )
        missing_product_id = (
            db.query(func.count(ProductMasterItem.id))
            .filter(ProductMasterItem.product_id.is_(None))
            .scalar()
            or 0
        )
        missing_supplier_id = (
            db.query(func.count(ProductMasterItem.id))
            .filter(ProductMasterItem.supplier_id.is_(None))
            .scalar()
            or 0
        )
        existing_product_suppliers = db.query(func.count(ProductSupplier.id)).scalar() or 0

        match_status_counts = (
            db.query(ProductMasterItem.match_status, func.count(ProductMasterItem.id))
            .group_by(ProductMasterItem.match_status)
            .order_by(func.count(ProductMasterItem.id).desc(), ProductMasterItem.match_status.asc())
            .all()
        )

        duplicate_supplier_sku = (
            db.query(
                ProductMasterItem.supplier_id,
                ProductMasterItem.sku,
                func.count(ProductMasterItem.id).label("row_count"),
            )
            .filter(
                ProductMasterItem.supplier_id.is_not(None),
                ProductMasterItem.sku.is_not(None),
            )
            .group_by(ProductMasterItem.supplier_id, ProductMasterItem.sku)
            .having(func.count(ProductMasterItem.id) > 1)
            .order_by(func.count(ProductMasterItem.id).desc())
            .limit(SAMPLE_LIMIT)
            .all()
        )

        duplicate_product_supplier_sku = (
            db.query(
                ProductMasterItem.product_id,
                ProductMasterItem.supplier_id,
                ProductMasterItem.sku,
                func.count(ProductMasterItem.id).label("row_count"),
            )
            .filter(
                ProductMasterItem.product_id.is_not(None),
                ProductMasterItem.supplier_id.is_not(None),
                ProductMasterItem.sku.is_not(None),
            )
            .group_by(ProductMasterItem.product_id, ProductMasterItem.supplier_id, ProductMasterItem.sku)
            .having(func.count(ProductMasterItem.id) > 1)
            .order_by(func.count(ProductMasterItem.id).desc())
            .limit(SAMPLE_LIMIT)
            .all()
        )

        conflict_count = (
            db.query(func.count(ProductMasterItem.id))
            .join(
                ProductSupplier,
                and_(
                    ProductSupplier.supplier_id == ProductMasterItem.supplier_id,
                    ProductSupplier.supplier_sku == ProductMasterItem.sku,
                ),
            )
            .filter(
                ProductMasterItem.supplier_id.is_not(None),
                ProductMasterItem.sku.is_not(None),
            )
            .scalar()
            or 0
        )

        eligible_count = (
            db.query(func.count(ProductMasterItem.id))
            .outerjoin(
                ProductSupplier,
                and_(
                    ProductSupplier.supplier_id == ProductMasterItem.supplier_id,
                    ProductSupplier.supplier_sku == ProductMasterItem.sku,
                ),
            )
            .filter(
                ProductMasterItem.product_id.is_not(None),
                ProductMasterItem.supplier_id.is_not(None),
                ProductMasterItem.sku.is_not(None),
                ProductSupplier.id.is_(None),
            )
            .scalar()
            or 0
        )

        eligible_sample = (
            db.query(
                ProductMasterItem.id,
                ProductMasterItem.product_id,
                ProductMasterItem.supplier_id,
                ProductMasterItem.sku,
                ProductMasterItem.name,
                ProductMasterItem.cost_price,
                ProductMasterItem.match_status,
                ProductMasterItem.match_method,
            )
            .outerjoin(
                ProductSupplier,
                and_(
                    ProductSupplier.supplier_id == ProductMasterItem.supplier_id,
                    ProductSupplier.supplier_sku == ProductMasterItem.sku,
                ),
            )
            .filter(
                ProductMasterItem.product_id.is_not(None),
                ProductMasterItem.supplier_id.is_not(None),
                ProductMasterItem.sku.is_not(None),
                ProductSupplier.id.is_(None),
            )
            .order_by(ProductMasterItem.id.asc())
            .limit(SAMPLE_LIMIT)
            .all()
        )

        problem_sample = (
            db.query(
                ProductMasterItem.id,
                ProductMasterItem.product_id,
                ProductMasterItem.supplier_id,
                ProductMasterItem.sku,
                ProductMasterItem.name,
                ProductMasterItem.match_status,
                ProductMasterItem.match_method,
            )
            .outerjoin(
                ProductSupplier,
                and_(
                    ProductSupplier.supplier_id == ProductMasterItem.supplier_id,
                    ProductSupplier.supplier_sku == ProductMasterItem.sku,
                ),
            )
            .filter(
                (ProductMasterItem.product_id.is_(None))
                | (ProductMasterItem.supplier_id.is_(None))
                | (ProductMasterItem.sku.is_(None))
                | (ProductSupplier.id.is_not(None))
            )
            .order_by(ProductMasterItem.id.asc())
            .limit(SAMPLE_LIMIT)
            .all()
        )

        print_section("ProductSupplier Backfill Diagnostic")
        print_count("Total ProductMasterItem rows", total_master_items)
        print_count("Rows with both product_id and supplier_id", with_product_and_supplier)
        print_count("Rows missing product_id", missing_product_id)
        print_count("Rows missing supplier_id", missing_supplier_id)
        print_count("Existing product_suppliers rows", existing_product_suppliers)
        print_count("Rows that look eligible for ProductSupplier backfill", eligible_count)
        print_count("Rows that would conflict with existing supplier_id + supplier_sku", conflict_count)

        print_section("ProductMasterItem match_status Counts")
        print_rows(match_status_counts)

        print_section("Duplicate supplier_id + sku Combinations")
        print_rows(duplicate_supplier_sku)

        print_section("Duplicate product_id + supplier_id + sku Combinations")
        print_rows(duplicate_product_supplier_sku)

        print_section("Sample Eligible Rows")
        print_rows(eligible_sample)

        print_section("Sample Skipped or Problem Rows")
        print_rows(problem_sample)

        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
