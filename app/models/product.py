from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Float, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    source_system: Mapped[str | None] = mapped_column(String(50), nullable=True, default="local")
    orderpro_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True, index=True)
    orderpro_sku: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    supplier_sku: Mapped[str | None] = mapped_column(String(255), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uom: Mapped[str | None] = mapped_column(String(50), nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    sell_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    hs_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country_of_origin: Mapped[str | None] = mapped_column(String(100), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    canonical_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seasonality_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_type: Mapped[str] = mapped_column(String(50), default="inventory")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_non_inventory: Mapped[bool] = mapped_column(Boolean, default=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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
    purchase_order_lines = relationship("PurchaseOrderLine", back_populates="product")
    supplier_record = relationship("Supplier", back_populates="products", foreign_keys=[supplier_id])
    orderpro_order_items = relationship("OrderProOrderItem", back_populates="product")
    seasonality_profile = relationship(
        "ProductSeasonalityProfile",
        back_populates="product",
        cascade="all, delete-orphan",
        uselist=False,
    )
    seasonality_backtests = relationship(
        "ProductSeasonalityBacktest",
        back_populates="product",
        cascade="all, delete-orphan",
    )
    forecast_input_profile = relationship(
        "ProductForecastInputProfile",
        back_populates="product",
        cascade="all, delete-orphan",
        uselist=False,
    )
    supplier_assignment_review = relationship(
        "ProductSupplierAssignmentReview",
        back_populates="product",
        cascade="all, delete-orphan",
        uselist=False,
    )
    stale_demand_review_decision = relationship(
        "StaleDemandReviewDecision",
        back_populates="product",
        cascade="all, delete-orphan",
        uselist=False,
    )
    pack_rules = relationship(
        "ProductPackRule",
        back_populates="product",
        cascade="all, delete-orphan",
    )
    historical_links = relationship(
        "ProductHistoricalLink",
        foreign_keys="ProductHistoricalLink.orderpro_product_id",
        back_populates="orderpro_product",
        cascade="all, delete-orphan",
    )
    orderpro_links = relationship(
        "ProductHistoricalLink",
        foreign_keys="ProductHistoricalLink.historical_product_id",
        back_populates="historical_product",
        cascade="all, delete-orphan",
    )
