from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProductForecastInputProfile(Base):
    __tablename__ = "product_forecast_input_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, unique=True, index=True)

    cost_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_source: Mapped[str] = mapped_column(String(100), nullable=False, default="missing")
    cost_confidence: Mapped[str] = mapped_column(String(50), nullable=False, default="missing")
    cost_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lead_time_source: Mapped[str] = mapped_column(String(100), nullable=False, default="missing")
    lead_time_confidence: Mapped[str] = mapped_column(String(50), nullable=False, default="missing")

    min_order_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    moq_source: Mapped[str] = mapped_column(String(100), nullable=False, default="missing")

    pack_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    pack_size_source: Mapped[str] = mapped_column(String(100), nullable=False, default="missing")

    safety_stock: Mapped[float | None] = mapped_column(Float, nullable=True)
    safety_stock_source: Mapped[str] = mapped_column(String(100), nullable=False, default="missing")

    blocking_issues: Mapped[list | None] = mapped_column(JSON, nullable=True)
    warning_issues: Mapped[list | None] = mapped_column(JSON, nullable=True)
    readiness_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    calculation_version: Mapped[str] = mapped_column(String(100), nullable=False, default="forecast-inputs-v1")
    calculated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    product = relationship("Product", back_populates="forecast_input_profile")
