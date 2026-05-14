from datetime import datetime, date

from sqlalchemy import Integer, Float, ForeignKey, String, DateTime, Date, UniqueConstraint
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
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)

    source_system: Mapped[str] = mapped_column(String(50), nullable=False, default="orderpro")
    location_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    on_hand: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    allocated: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    incoming: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    available: Mapped[float] = mapped_column(Float, nullable=False, default=0)

    incoming_eta: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    product = relationship("Product", back_populates="inventory_positions")