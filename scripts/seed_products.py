from datetime import date, timedelta

from app.db.session import SessionLocal
from app.models.product import Product
from app.models.usage_history import UsageHistory


def seed():
    db = SessionLocal()

    try:
        if db.query(Product).count() > 0:
            print("Products already exist. Skipping seed.")
            return

        products = [
            Product(
                name="Printer Paper A4",
                supplier="Office Supplies Co.",
                current_stock=180,
                safety_stock=50,
                lead_time_days=7,
                min_order_qty=100,
            ),
            Product(
                name="Coffee Beans 1kg",
                supplier="Premium Roasters",
                current_stock=22,
                safety_stock=10,
                lead_time_days=5,
                min_order_qty=20,
            ),
            Product(
                name="Thermal Receipt Rolls",
                supplier="Retail Essentials",
                current_stock=300,
                safety_stock=80,
                lead_time_days=10,
                min_order_qty=50,
            ),
        ]

        db.add_all(products)
        db.commit()

        inserted_products = db.query(Product).all()
        product_map = {p.name: p.id for p in inserted_products}

        today = date.today()

        usage_entries = []
        for i in range(14):
            usage_entries.extend(
                [
                    UsageHistory(
                        product_id=product_map["Printer Paper A4"],
                        date=today - timedelta(days=i),
                        qty_used=28,
                    ),
                    UsageHistory(
                        product_id=product_map["Coffee Beans 1kg"],
                        date=today - timedelta(days=i),
                        qty_used=4,
                    ),
                    UsageHistory(
                        product_id=product_map["Thermal Receipt Rolls"],
                        date=today - timedelta(days=i),
                        qty_used=12,
                    ),
                ]
            )

        db.add_all(usage_entries)
        db.commit()

        print("Seed completed successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    seed()