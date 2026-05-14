from sqlalchemy import Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    email: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(255), nullable=True)

    lead_time_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lead_time_min_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lead_time_max_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    active_skus: Mapped[int] = mapped_column(Integer, default=0)
    lead_time_needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    aliases = relationship("SupplierAlias", back_populates="supplier", cascade="all, delete-orphan")
    master_items = relationship("ProductMasterItem", back_populates="supplier")