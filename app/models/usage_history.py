from datetime import date

from sqlalchemy import Integer, Float, ForeignKey, Date, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UsageHistory(Base):
    __tablename__ = "usage_history"
    __table_args__ = (
        UniqueConstraint("product_id", "date", "source_system", name="uq_usage_history_product_date_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    qty_used: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    qty_returned: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    net_qty: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    gross_revenue: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, default="historical_sales_excel")

    product = relationship("Product", back_populates="usage_history")