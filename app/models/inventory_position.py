from datetime import datetime, date

from sqlalchemy import Integer, Float, ForeignKey, String, DateTime, Date, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InventoryPosition(Base):
    __tablename__ = "inventory_positions"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "source_system",
            "location_code",
            name="uq_inventory_positions_product_source_location",
        ),
        Index(
            "ix_inventory_positions_product_warehouse_location_lot",
            "product_id",
            "warehouse_id",
            "location_id",
            "lot_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"), nullable=True, index=True)
    orderpro_inventory_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)
    orderpro_product_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    orderpro_warehouse_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    source_system: Mapped[str] = mapped_column(String(50), nullable=False, default="orderpro")
    location_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    lot_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    lot: Mapped[str | None] = mapped_column(String(255), nullable=True)

    on_hand: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    allocated: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    incoming: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    available: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    quantity_on_hand: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    quantity_available: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity_allocated: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity_incoming: Mapped[float | None] = mapped_column(Float, nullable=True)

    incoming_eta: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    product = relationship("Product", back_populates="inventory_positions")
    warehouse = relationship("Warehouse", back_populates="inventory_positions")
