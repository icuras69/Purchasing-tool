from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    orderpro_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)
    orderpro_code: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)
    source_system: Mapped[str | None] = mapped_column(String(50), nullable=True, default="local")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    local_profile_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    email: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(255), nullable=True)

    lead_time_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lead_time_min_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lead_time_max_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    active_skus: Mapped[int] = mapped_column(Integer, default=0)
    lead_time_needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    aliases = relationship("SupplierAlias", back_populates="supplier", cascade="all, delete-orphan")
    master_items = relationship("ProductMasterItem", back_populates="supplier")
    product_suppliers = relationship("ProductSupplier", back_populates="supplier", cascade="all, delete-orphan")
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")
    products = relationship("Product", back_populates="supplier_record", foreign_keys="Product.supplier_id")
