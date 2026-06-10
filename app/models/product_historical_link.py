from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProductHistoricalLink(Base):
    __tablename__ = "product_historical_links"
    __table_args__ = (
        UniqueConstraint(
            "orderpro_product_id",
            "historical_product_id",
            name="uq_product_historical_links_pair",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    orderpro_product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    historical_product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    match_method: Mapped[str] = mapped_column(String(50), nullable=False)
    match_value: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    confidence_label: Mapped[str] = mapped_column(String(50), nullable=False, default="low")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="needs_review", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    orderpro_product = relationship("Product", foreign_keys=[orderpro_product_id], back_populates="historical_links")
    historical_product = relationship("Product", foreign_keys=[historical_product_id], back_populates="orderpro_links")
