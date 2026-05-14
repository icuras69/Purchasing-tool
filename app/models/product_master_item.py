from sqlalchemy import Integer, String, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProductMasterItem(Base):
    __tablename__ = "product_master_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    sku: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    supplier_name_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)

    warehouse: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cost_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    sales_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_sales: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_code: Mapped[str | None] = mapped_column(String(100), nullable=True)

    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)

    match_status: Mapped[str] = mapped_column(String(50), default="unmatched")
    match_method: Mapped[str | None] = mapped_column(String(50), nullable=True)

    supplier = relationship("Supplier", back_populates="master_items")
    product = relationship("Product", back_populates="master_items")