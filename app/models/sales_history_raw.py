from datetime import date

from sqlalchemy import (
    Integer,
    Float,
    ForeignKey,
    Date,
    String,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SalesHistoryRaw(Base):
    __tablename__ = "sales_history_raw"
    __table_args__ = (
        UniqueConstraint(
            "source_workbook",
            "source_sheet",
            "source_row_number",
            name="uq_sales_history_raw_source_row",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    source_workbook: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sheet: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)

    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode_clean: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    batch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoice: Mapped[str | None] = mapped_column(String(100), nullable=True)
    txn_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    vat_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross: Mapped[float | None] = mapped_column(Float, nullable=True)
    code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sales_person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purchase_order_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nett: Mapped[float | None] = mapped_column(Float, nullable=True)
    vat: Mapped[float | None] = mapped_column(Float, nullable=True)

    source_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    row_type: Mapped[str] = mapped_column(String(50), nullable=False, default="inventory")
    is_non_inventory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_return: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    product = relationship("Product", back_populates="sales_history_raw")