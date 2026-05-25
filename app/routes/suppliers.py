from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier
from app.routes.product_suppliers import serialize_product_supplier
from app.schemas.product_supplier import ProductSupplierMappingResponse

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("/{supplier_id}/products", response_model=list[ProductSupplierMappingResponse])
def list_supplier_products(supplier_id: int, db: Session = Depends(get_db)):
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found.")

    mappings = (
        db.query(ProductSupplier)
        .options(
            selectinload(ProductSupplier.product),
            selectinload(ProductSupplier.supplier),
        )
        .filter(ProductSupplier.supplier_id == supplier_id)
        .order_by(ProductSupplier.product_id.asc(), ProductSupplier.id.asc())
        .all()
    )
    return [serialize_product_supplier(mapping) for mapping in mappings]
