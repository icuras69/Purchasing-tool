from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier
from app.schemas.product_supplier import (
    ProductSupplierCreate,
    ProductSupplierMappingResponse,
    ProductSupplierUpdate,
)

router = APIRouter(prefix="/product-suppliers", tags=["product-suppliers"])

REJECTED_STATUS = "rejected"


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


def load_mapping(db: Session, mapping_id: int) -> ProductSupplier:
    mapping = (
        db.query(ProductSupplier)
        .options(
            selectinload(ProductSupplier.product),
            selectinload(ProductSupplier.supplier),
        )
        .filter(ProductSupplier.id == mapping_id)
        .first()
    )
    if not mapping:
        raise HTTPException(status_code=404, detail="ProductSupplier mapping not found.")
    return mapping


def validate_product_and_supplier(db: Session, product_id: int, supplier_id: int) -> None:
    if not db.get(Product, product_id):
        raise HTTPException(status_code=404, detail="Product not found.")
    if not db.get(Supplier, supplier_id):
        raise HTTPException(status_code=404, detail="Supplier not found.")


def validate_mapping_uniqueness(
    db: Session,
    *,
    product_id: int,
    supplier_id: int,
    supplier_sku: str | None,
    exclude_mapping_id: int | None = None,
) -> None:
    if supplier_sku:
        duplicate_supplier_sku = db.query(ProductSupplier).filter(
            ProductSupplier.supplier_id == supplier_id,
            ProductSupplier.supplier_sku == supplier_sku,
        )
        if exclude_mapping_id is not None:
            duplicate_supplier_sku = duplicate_supplier_sku.filter(ProductSupplier.id != exclude_mapping_id)
        if duplicate_supplier_sku.first():
            raise HTTPException(
                status_code=409,
                detail="A mapping with this supplier_id and supplier_sku already exists.",
            )

    duplicate_product_supplier_sku = db.query(ProductSupplier).filter(
        ProductSupplier.product_id == product_id,
        ProductSupplier.supplier_id == supplier_id,
    )
    if supplier_sku is None:
        duplicate_product_supplier_sku = duplicate_product_supplier_sku.filter(
            ProductSupplier.supplier_sku.is_(None)
        )
    else:
        duplicate_product_supplier_sku = duplicate_product_supplier_sku.filter(
            ProductSupplier.supplier_sku == supplier_sku
        )
    if exclude_mapping_id is not None:
        duplicate_product_supplier_sku = duplicate_product_supplier_sku.filter(
            ProductSupplier.id != exclude_mapping_id
        )
    if duplicate_product_supplier_sku.first():
        raise HTTPException(
            status_code=409,
            detail="A mapping with this product_id, supplier_id, and supplier_sku already exists.",
        )


def refresh_mapping(db: Session, mapping: ProductSupplier) -> ProductSupplier:
    db.commit()
    return load_mapping(db, mapping.id)


@router.get("", response_model=list[ProductSupplierMappingResponse])
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


@router.post("", response_model=ProductSupplierMappingResponse, status_code=status.HTTP_201_CREATED)
def create_product_supplier_mapping(payload: ProductSupplierCreate, db: Session = Depends(get_db)):
    validate_product_and_supplier(db, payload.product_id, payload.supplier_id)
    validate_mapping_uniqueness(
        db,
        product_id=payload.product_id,
        supplier_id=payload.supplier_id,
        supplier_sku=payload.supplier_sku,
    )

    if payload.match_status == REJECTED_STATUS:
        is_preferred = False
    else:
        is_preferred = False

    now = datetime.utcnow()
    mapping = ProductSupplier(
        product_id=payload.product_id,
        supplier_id=payload.supplier_id,
        supplier_sku=payload.supplier_sku,
        supplier_product_name=payload.supplier_product_name,
        purchase_price=payload.purchase_price,
        currency=payload.currency,
        minimum_order_quantity=payload.minimum_order_quantity,
        pack_size=payload.pack_size,
        lead_time_days=payload.lead_time_days,
        is_preferred=is_preferred,
        match_status=payload.match_status,
        match_method=payload.match_method,
        match_confidence=payload.match_confidence,
        created_at=now,
        updated_at=now,
    )
    db.add(mapping)
    db.commit()
    return serialize_product_supplier(load_mapping(db, mapping.id))


@router.patch("/{mapping_id}", response_model=ProductSupplierMappingResponse)
def update_product_supplier_mapping(
    mapping_id: int,
    payload: ProductSupplierUpdate,
    db: Session = Depends(get_db),
):
    mapping = load_mapping(db, mapping_id)
    changes = payload.model_dump(exclude_unset=True)

    if "supplier_sku" in changes:
        validate_mapping_uniqueness(
            db,
            product_id=mapping.product_id,
            supplier_id=mapping.supplier_id,
            supplier_sku=changes["supplier_sku"],
            exclude_mapping_id=mapping.id,
        )

    for field, value in changes.items():
        setattr(mapping, field, value)

    if mapping.match_status == REJECTED_STATUS:
        mapping.is_preferred = False

    mapping.updated_at = datetime.utcnow()
    return serialize_product_supplier(refresh_mapping(db, mapping))


@router.post("/{mapping_id}/set-preferred", response_model=ProductSupplierMappingResponse)
def set_preferred_product_supplier_mapping(mapping_id: int, db: Session = Depends(get_db)):
    mapping = load_mapping(db, mapping_id)
    if mapping.match_status == REJECTED_STATUS:
        raise HTTPException(status_code=400, detail="Rejected mappings cannot be preferred.")

    now = datetime.utcnow()
    other_mappings = (
        db.query(ProductSupplier)
        .filter(
            ProductSupplier.product_id == mapping.product_id,
            ProductSupplier.id != mapping.id,
        )
        .all()
    )
    for other_mapping in other_mappings:
        if other_mapping.is_preferred:
            other_mapping.is_preferred = False
            other_mapping.updated_at = now

    mapping.is_preferred = True
    mapping.updated_at = now
    return serialize_product_supplier(refresh_mapping(db, mapping))


@router.post("/{mapping_id}/unset-preferred", response_model=ProductSupplierMappingResponse)
def unset_preferred_product_supplier_mapping(mapping_id: int, db: Session = Depends(get_db)):
    mapping = load_mapping(db, mapping_id)
    mapping.is_preferred = False
    mapping.updated_at = datetime.utcnow()
    return serialize_product_supplier(refresh_mapping(db, mapping))


@router.post("/{mapping_id}/confirm", response_model=ProductSupplierMappingResponse)
def confirm_product_supplier_mapping(mapping_id: int, db: Session = Depends(get_db)):
    mapping = load_mapping(db, mapping_id)
    mapping.match_status = "confirmed"
    mapping.updated_at = datetime.utcnow()
    return serialize_product_supplier(refresh_mapping(db, mapping))


@router.post("/{mapping_id}/reject", response_model=ProductSupplierMappingResponse)
def reject_product_supplier_mapping(mapping_id: int, db: Session = Depends(get_db)):
    mapping = load_mapping(db, mapping_id)
    mapping.match_status = REJECTED_STATUS
    mapping.is_preferred = False
    mapping.updated_at = datetime.utcnow()
    return serialize_product_supplier(refresh_mapping(db, mapping))
