from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProductSeasonalityBacktest(Base):
    __tablename__ = "product_seasonality_backtests"
    __table_args__ = (
        UniqueConstraint("product_id", "backtest_version", name="uq_product_seasonality_backtest_product_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)

    readiness_status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    activation_recommendation: Mapped[str] = mapped_column(String(100), nullable=False, default="insufficient_evidence")
    seasonal_improvement_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_wape: Mapped[float | None] = mapped_column(Float, nullable=True)
    seasonal_wape: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    seasonal_mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_bias: Mapped[float | None] = mapped_column(Float, nullable=True)
    seasonal_bias: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluated_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluated_years: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recommended_max_multiplier: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    backtest_version: Mapped[str] = mapped_column(String(50), nullable=False, default="seasonality-backtest-v1", index=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    product = relationship("Product", back_populates="seasonality_backtests")
