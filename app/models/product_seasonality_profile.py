from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProductSeasonalityProfile(Base):
    __tablename__ = "product_seasonality_profiles"
    __table_args__ = (
        UniqueConstraint("product_id", name="uq_product_seasonality_profiles_product_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)

    history_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    history_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    history_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    years_covered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    total_units: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    average_monthly_units: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    monthly_units: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    monthly_indices: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    peak_months: Mapped[list | None] = mapped_column(JSON, nullable=True)
    low_months: Mapped[list | None] = mapped_column(JSON, nullable=True)

    primary_season: Mapped[str | None] = mapped_column(String(50), nullable=True)
    seasonality_tag: Mapped[str] = mapped_column(String(100), nullable=False, default="insufficient_data", index=True)
    seasonality_strength: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    confidence_label: Mapped[str] = mapped_column(String(50), nullable=False, default="insufficient", index=True)
    coefficient_of_variation: Mapped[float | None] = mapped_column(Float, nullable=True)

    calculation_version: Mapped[str] = mapped_column(String(50), nullable=False, default="seasonality-v1")
    calculated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    product = relationship("Product", back_populates="seasonality_profile")
