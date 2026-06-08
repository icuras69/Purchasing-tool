from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OrderProOrder(Base):
    __tablename__ = "orderpro_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    orderpro_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    order_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    order_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    required_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shipped_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    orderpro_warehouse_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subtotal: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    shipping_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    raw_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    items = relationship("OrderProOrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderProOrderItem(Base):
    __tablename__ = "orderpro_order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "orderpro_line_key", name="uq_orderpro_order_items_order_line_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    orderpro_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    orderpro_line_key: Mapped[str] = mapped_column(String(255), nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("orderpro_orders.id"), nullable=False, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    orderpro_product_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    sku: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    quantity_ordered: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity_picked: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity_shipped: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    order = relationship("OrderProOrder", back_populates="items")
    product = relationship("Product", back_populates="orderpro_order_items")
