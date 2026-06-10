from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OrderProPurchaseOrder(Base):
    __tablename__ = "orderpro_purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    orderpro_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    purchase_order_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    orderpro_supplier_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    supplier_code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    order_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expected_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    received_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    supplier = relationship("Supplier")
    lines = relationship("OrderProPurchaseOrderLine", back_populates="purchase_order", cascade="all, delete-orphan")


class OrderProPurchaseOrderLine(Base):
    __tablename__ = "orderpro_purchase_order_lines"
    __table_args__ = (
        UniqueConstraint("orderpro_purchase_order_id", "orderpro_line_key", name="uq_orderpro_po_lines_order_line_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    orderpro_purchase_order_id: Mapped[int] = mapped_column(ForeignKey("orderpro_purchase_orders.id"), nullable=False, index=True)
    orderpro_line_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    orderpro_line_key: Mapped[str] = mapped_column(String(255), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    orderpro_product_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    sku: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity_ordered: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity_received: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity_cancelled: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity_open: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    unit_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    purchase_order = relationship("OrderProPurchaseOrder", back_populates="lines")
    product = relationship("Product")
