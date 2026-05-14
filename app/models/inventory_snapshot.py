from datetime import date

from sqlalchemy import Integer, Float, ForeignKey, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    stock_on_hand: Mapped[float] = mapped_column(Float, nullable=False)

    product = relationship("Product", back_populates="inventory_snapshots")