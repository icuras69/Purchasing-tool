from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SupplierAlias(Base):
    __tablename__ = "supplier_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False, index=True)

    alias_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    normalized_alias_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    supplier = relationship("Supplier", back_populates="aliases")