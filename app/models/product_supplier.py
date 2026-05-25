from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProductSupplier(Base):
    __tablename__ = "product_suppliers"
    __table_args__ = (
        Index("ix_product_suppliers_product_id", "product_id"),
        Index("ix_product_suppliers_supplier_id", "supplier_id"),
        Index(
            "uq_product_suppliers_supplier_sku_not_null",
            "supplier_id",
            "supplier_sku",
            unique=True,
            postgresql_where=text("supplier_sku IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)

    supplier_sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier_product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purchase_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    minimum_order_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    pack_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    match_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    match_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    product = relationship("Product", back_populates="product_suppliers")
    supplier = relationship("Supplier", back_populates="product_suppliers")
