from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProductPackRule(Base):
    __tablename__ = "product_pack_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    canonical_sku: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    rule_scope: Mapped[str] = mapped_column(String(50), nullable=False, default="product")
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    order_multiple: Mapped[float] = mapped_column(Float, nullable=False)
    pack_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    units_per_box: Mapped[float | None] = mapped_column(Float, nullable=True)
    units_per_pallet: Mapped[float | None] = mapped_column(Float, nullable=True)
    pallet_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    product = relationship("Product", back_populates="pack_rules")
    supplier = relationship("Supplier")
