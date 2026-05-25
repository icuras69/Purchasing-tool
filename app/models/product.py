from sqlalchemy import Integer, String, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    canonical_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seasonality_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_type: Mapped[str] = mapped_column(String(50), default="inventory")
    is_non_inventory: Mapped[bool] = mapped_column(Boolean, default=False)

    current_stock: Mapped[float] = mapped_column(Float, default=0)
    safety_stock: Mapped[float] = mapped_column(Float, default=0)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0)
    min_order_qty: Mapped[float] = mapped_column(Float, default=1)

    purchase_orders = relationship("PurchaseOrder", back_populates="product", cascade="all, delete-orphan")
    usage_history = relationship("UsageHistory", back_populates="product", cascade="all, delete-orphan")
    inventory_snapshots = relationship("InventorySnapshot", back_populates="product", cascade="all, delete-orphan")
    inventory_positions = relationship("InventoryPosition", back_populates="product", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="product", cascade="all, delete-orphan")
    sales_history_raw = relationship("SalesHistoryRaw", back_populates="product", cascade="all, delete-orphan")
    master_items = relationship("ProductMasterItem", back_populates="product")
    product_suppliers = relationship("ProductSupplier", back_populates="product", cascade="all, delete-orphan")
