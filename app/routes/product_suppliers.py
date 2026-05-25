from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.product_supplier import ProductSupplier
from app.schemas.product_supplier import ProductSupplierMappingResponse

router = APIRouter(prefix="/product-suppliers", tags=["product-suppliers"])


def serialize_product_supplier(mapping: ProductSupplier) -> dict:
    return {
        "id": mapping.id,
        "product_id": mapping.product_id,
        "product_name": mapping.product.name if mapping.product else None,
        "supplier_id": mapping.supplier_id,
        "supplier_name": mapping.supplier.name if mapping.supplier else None,
        "supplier_sku": mapping.supplier_sku,
        "supplier_product_name": mapping.supplier_product_name,
        "purchase_price": mapping.purchase_price,
        "currency": mapping.currency,
        "minimum_order_quantity": mapping.minimum_order_quantity,
        "pack_size": mapping.pack_size,
        "lead_time_days": mapping.lead_time_days,
        "is_preferred": mapping.is_preferred,
        "match_status": mapping.match_status,
        "match_method": mapping.match_method,
        "match_confidence": mapping.match_confidence,
        "last_synced_at": mapping.last_synced_at,
    }


@router.get("/", response_model=list[ProductSupplierMappingResponse])
def list_product_suppliers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    mappings = (
        db.query(ProductSupplier)
        .options(
            selectinload(ProductSupplier.product),
            selectinload(ProductSupplier.supplier),
        )
        .order_by(ProductSupplier.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [serialize_product_supplier(mapping) for mapping in mappings]
