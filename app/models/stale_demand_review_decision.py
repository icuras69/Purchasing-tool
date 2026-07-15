from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StaleDemandReviewDecision(Base):
    __tablename__ = "stale_demand_review_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    recommendation_id: Mapped[int | None] = mapped_column(
        ForeignKey("recommendations.id"),
        nullable=True,
        index=True,
    )
    decision: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    reviewed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    product = relationship("Product", back_populates="stale_demand_review_decision")
    recommendation = relationship("Recommendation")
