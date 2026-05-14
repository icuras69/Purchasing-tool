from datetime import datetime, date

from sqlalchemy import Integer, Float, ForeignKey, Date, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    recommended_order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    recommended_qty: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False, default="low")
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    product = relationship("Product", back_populates="recommendations")