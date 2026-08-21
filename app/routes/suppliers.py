from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier
from app.routes.product_suppliers import serialize_product_supplier
from app.routes.purchase_orders import serialize_purchase_order, serialize_skipped_products
from app.schemas.purchase_order import (
    DraftPurchaseOrderFromProductsResponse,
    SupplierDraftPurchaseOrderFromForecastCreate,
    SupplierForecastResponse,
)
from app.schemas.product_supplier import ProductSupplierMappingResponse
from app.schemas.supplier import SupplierResponse, SupplierUpdate
from app.services.purchase_order_drafting import (
    DraftPurchaseOrderError,
    build_supplier_forecast,
    create_draft_po_from_supplier_forecast,
)

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def serialize_supplier(supplier: Supplier) -> dict:
    products = supplier.products
    return {
        "id": supplier.id,
        "name": supplier.name,
        "orderpro_id": supplier.orderpro_id,
        "orderpro_code": supplier.orderpro_code,
        "source_system": supplier.source_system,
        "is_active": supplier.is_active,
        "local_profile_override": supplier.local_profile_override,
        "last_synced_at": supplier.last_synced_at,
        "email": supplier.email,
        "phone": supplier.phone,
        "website": supplier.website,
        "contact_method": supplier.contact_method,
        "payment_terms": supplier.payment_terms,
        "lead_time_raw": supplier.lead_time_raw,
        "lead_time_days": supplier.lead_time_days,
        "lead_time_min_days": supplier.lead_time_min_days,
        "lead_time_max_days": supplier.lead_time_max_days,
        "notes": supplier.notes,
        "active_skus": supplier.active_skus,
        "lead_time_needs_review": supplier.lead_time_needs_review,
        "product_count": len(products),
        "active_product_count": sum(1 for product in products if product.is_active),
        "writes_to_orderpro": False,
    }


@router.get("", response_model=list[SupplierResponse])
def list_suppliers(db: Session = Depends(get_db)):
    suppliers = (
        db.query(Supplier)
        .options(selectinload(Supplier.products))
        .order_by(Supplier.name.asc())
        .all()
    )
    return [serialize_supplier(supplier) for supplier in suppliers]


@router.get("/{supplier_id}", response_model=SupplierResponse)
def get_supplier(supplier_id: int, db: Session = Depends(get_db)):
    supplier = (
        db.query(Supplier)
        .options(selectinload(Supplier.products))
        .filter(Supplier.id == supplier_id)
        .one_or_none()
    )
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    return serialize_supplier(supplier)


@router.patch("/{supplier_id}", response_model=SupplierResponse)
def update_supplier(
    supplier_id: int,
    payload: SupplierUpdate,
    db: Session = Depends(get_db),
):
    supplier = (
        db.query(Supplier)
        .options(selectinload(Supplier.products))
        .filter(Supplier.id == supplier_id)
        .one_or_none()
    )
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found.")

    changes = payload.model_dump(exclude_unset=True)
    final_lead_time_days = changes.get("lead_time_days", supplier.lead_time_days)
    final_min_days = changes.get("lead_time_min_days", supplier.lead_time_min_days)
    final_max_days = changes.get("lead_time_max_days", supplier.lead_time_max_days)
    if final_min_days is not None and final_max_days is not None and final_min_days > final_max_days:
        raise HTTPException(
            status_code=422,
            detail="Minimum lead time cannot be greater than maximum lead time.",
        )
    if (
        final_lead_time_days is not None
        and final_min_days is not None
        and final_lead_time_days < final_min_days
    ):
        raise HTTPException(status_code=422, detail="Lead time cannot be below the minimum lead time.")
    if (
        final_lead_time_days is not None
        and final_max_days is not None
        and final_lead_time_days > final_max_days
    ):
        raise HTTPException(status_code=422, detail="Lead time cannot exceed the maximum lead time.")

    for field, value in changes.items():
        setattr(supplier, field, value)
    if changes:
        supplier.local_profile_override = True
    if "lead_time_days" in changes:
        if final_lead_time_days is None:
            supplier.lead_time_raw = None
            supplier.lead_time_needs_review = True
        else:
            supplier.lead_time_raw = f"{final_lead_time_days} days"
            supplier.lead_time_needs_review = False

    db.commit()
    db.refresh(supplier)
    return serialize_supplier(supplier)


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


@router.get("/{supplier_id}/forecast", response_model=SupplierForecastResponse)
def get_supplier_forecast(supplier_id: int, db: Session = Depends(get_db)):
    try:
        return build_supplier_forecast(db, supplier_id)
    except DraftPurchaseOrderError as error:
        raise HTTPException(status_code=404, detail=error.message) from error


@router.post(
    "/{supplier_id}/draft-po-from-forecast",
    response_model=DraftPurchaseOrderFromProductsResponse,
    status_code=201,
)
def create_supplier_draft_po_from_forecast(
    supplier_id: int,
    payload: SupplierDraftPurchaseOrderFromForecastCreate | None = None,
    db: Session = Depends(get_db),
):
    payload = payload or SupplierDraftPurchaseOrderFromForecastCreate()
    try:
        result = create_draft_po_from_supplier_forecast(
            db,
            supplier_id=supplier_id,
            created_by=payload.created_by,
            notes=payload.notes,
            only_reorder_needed=payload.only_reorder_needed,
        )
    except DraftPurchaseOrderError as error:
        status_code = 404 if error.message == "Supplier not found." else 400
        raise HTTPException(
            status_code=status_code,
            detail={
                "message": error.message,
                "skipped_products": serialize_skipped_products(error.skipped_products),
            },
        ) from error

    purchase_orders = [serialize_purchase_order(po) for po in result.purchase_orders]
    return {
        "purchase_order": purchase_orders[0] if len(purchase_orders) == 1 else None,
        "created_purchase_orders": purchase_orders,
        "summary": {
            "created_po_count": len(purchase_orders),
            "created_line_count": result.created_line_count,
            "skipped_products": serialize_skipped_products(result.skipped_products),
            "grouped_by_supplier": {
                str(supplier_id): line_count
                for supplier_id, line_count in result.grouped_by_supplier.items()
            },
        },
    }
