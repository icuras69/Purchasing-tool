from datetime import datetime, date

from sqlalchemy import Integer, Float, ForeignKey, Date, DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    product_supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_suppliers.id"),
        nullable=True,
        index=True,
    )
    converted_purchase_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_orders.id"),
        nullable=True,
        index=True,
    )

    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    recommended_order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    recommended_qty: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False, default="low")
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    recommendation_type: Mapped[str] = mapped_column(String(50), default="reorder", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="pending_review", nullable=False, index=True)
    recommended_supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recommended_supplier_sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estimated_unit_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_total_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    forecast_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    supplier_context_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    generated_by: Mapped[str] = mapped_column(String(50), default="system", nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    product = relationship("Product", back_populates="recommendations")
    supplier = relationship("Supplier")
    product_supplier = relationship("ProductSupplier")
    converted_purchase_order = relationship("PurchaseOrder")
