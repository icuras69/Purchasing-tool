from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier
from app.schemas.purchase_order import (
    PurchaseOrderApprove,
    PurchaseOrderCreate,
    PurchaseOrderLineCreate,
    PurchaseOrderLineResponse,
    PurchaseOrderLineUpdate,
    PurchaseOrderResponse,
)

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])

DRAFT = "draft"
PENDING_APPROVAL = "pending_approval"
APPROVED = "approved"
ISSUED = "issued"
RECEIVED = "received"
CANCELLED = "cancelled"
REJECTED_MAPPING = "rejected"


def serialize_line(line: PurchaseOrderLine) -> dict:
    return {
        "id": line.id,
        "purchase_order_id": line.purchase_order_id,
        "product_id": line.product_id,
        "product_supplier_id": line.product_supplier_id,
        "supplier_sku": line.supplier_sku,
        "supplier_product_name": line.supplier_product_name,
        "quantity": line.quantity,
        "unit_cost": line.unit_cost,
        "currency": line.currency,
        "line_total": line.line_total,
        "minimum_order_quantity": line.minimum_order_quantity,
        "pack_size": line.pack_size,
        "lead_time_days": line.lead_time_days,
        "notes": line.notes,
    }


def serialize_purchase_order(po: PurchaseOrder) -> dict:
    return {
        "id": po.id,
        "supplier_id": po.supplier_id,
        "supplier_name": po.supplier.name if po.supplier else None,
        "status": po.status,
        "created_at": po.created_at,
        "updated_at": po.updated_at,
        "approved_at": po.approved_at,
        "issued_at": po.issued_at,
        "received_at": po.received_at,
        "cancelled_at": po.cancelled_at,
        "notes": po.notes,
        "total_amount": po.total_amount,
        "currency": po.currency,
        "created_by": po.created_by,
        "approved_by": po.approved_by,
        "lines": [serialize_line(line) for line in po.lines],
    }


def load_purchase_order(db: Session, po_id: int) -> PurchaseOrder:
    po = (
        db.query(PurchaseOrder)
        .options(
            selectinload(PurchaseOrder.supplier),
            selectinload(PurchaseOrder.lines),
        )
        .filter(PurchaseOrder.id == po_id)
        .first()
    )
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    return po


def load_line(db: Session, po_id: int, line_id: int) -> PurchaseOrderLine:
    line = (
        db.query(PurchaseOrderLine)
        .filter(
            PurchaseOrderLine.purchase_order_id == po_id,
            PurchaseOrderLine.id == line_id,
        )
        .first()
    )
    if not line:
        raise HTTPException(status_code=404, detail="Purchase order line not found.")
    return line


def require_draft(po: PurchaseOrder) -> None:
    if po.status != DRAFT:
        raise HTTPException(status_code=400, detail="Only draft purchase orders can be edited.")


def calculate_line_total(quantity: float, unit_cost: float | None) -> float | None:
    if unit_cost is None:
        return None
    return round(quantity * unit_cost, 2)


def recalculate_total(po: PurchaseOrder) -> None:
    totals = [line.line_total for line in po.lines if line.line_total is not None]
    po.total_amount = round(sum(totals), 2) if totals else None
    currencies = {line.currency for line in po.lines if line.currency}
    if len(currencies) == 1:
        po.currency = currencies.pop()


def snapshot_line(po: PurchaseOrder, product_supplier: ProductSupplier, payload: PurchaseOrderLineCreate) -> PurchaseOrderLine:
    quantity = payload.quantity
    return PurchaseOrderLine(
        purchase_order_id=po.id,
        product_id=product_supplier.product_id,
        product_supplier_id=product_supplier.id,
        supplier_sku=product_supplier.supplier_sku,
        supplier_product_name=product_supplier.supplier_product_name,
        quantity=quantity,
        unit_cost=product_supplier.purchase_price,
        currency=product_supplier.currency,
        line_total=calculate_line_total(quantity, product_supplier.purchase_price),
        minimum_order_quantity=product_supplier.minimum_order_quantity,
        pack_size=product_supplier.pack_size,
        lead_time_days=product_supplier.lead_time_days,
        notes=payload.notes,
    )


@router.post("", response_model=PurchaseOrderResponse, status_code=status.HTTP_201_CREATED)
def create_purchase_order(payload: PurchaseOrderCreate, db: Session = Depends(get_db)):
    supplier = db.get(Supplier, payload.supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found.")

    now = datetime.utcnow()
    po = PurchaseOrder(
        supplier_id=payload.supplier_id,
        status=DRAFT,
        created_at=now,
        updated_at=now,
        notes=payload.notes,
        currency=payload.currency,
        created_by=payload.created_by,
    )
    db.add(po)
    db.commit()
    return serialize_purchase_order(load_purchase_order(db, po.id))


@router.get("", response_model=list[PurchaseOrderResponse])
def list_purchase_orders(db: Session = Depends(get_db)):
    purchase_orders = (
        db.query(PurchaseOrder)
        .options(
            selectinload(PurchaseOrder.supplier),
            selectinload(PurchaseOrder.lines),
        )
        .order_by(PurchaseOrder.id.asc())
        .all()
    )
    return [serialize_purchase_order(po) for po in purchase_orders]


@router.get("/{po_id}", response_model=PurchaseOrderResponse)
def get_purchase_order(po_id: int, db: Session = Depends(get_db)):
    return serialize_purchase_order(load_purchase_order(db, po_id))


@router.post("/{po_id}/lines", response_model=PurchaseOrderResponse, status_code=status.HTTP_201_CREATED)
def add_purchase_order_line(
    po_id: int,
    payload: PurchaseOrderLineCreate,
    db: Session = Depends(get_db),
):
    po = load_purchase_order(db, po_id)
    require_draft(po)

    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero.")

    product_supplier = db.get(ProductSupplier, payload.product_supplier_id)
    if not product_supplier:
        raise HTTPException(status_code=404, detail="ProductSupplier mapping not found.")
    if product_supplier.supplier_id != po.supplier_id:
        raise HTTPException(status_code=400, detail="ProductSupplier belongs to a different supplier.")
    if product_supplier.match_status == REJECTED_MAPPING:
        raise HTTPException(status_code=400, detail="Rejected ProductSupplier mappings cannot be used.")

    line = snapshot_line(po, product_supplier, payload)
    po.lines.append(line)
    po.updated_at = datetime.utcnow()
    recalculate_total(po)
    db.add(line)
    db.commit()
    return serialize_purchase_order(load_purchase_order(db, po.id))


@router.patch("/{po_id}/lines/{line_id}", response_model=PurchaseOrderResponse)
def update_purchase_order_line(
    po_id: int,
    line_id: int,
    payload: PurchaseOrderLineUpdate,
    db: Session = Depends(get_db),
):
    po = load_purchase_order(db, po_id)
    require_draft(po)
    line = load_line(db, po_id, line_id)
    changes = payload.model_dump(exclude_unset=True)

    if "quantity" in changes:
        if changes["quantity"] is None or changes["quantity"] <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be greater than zero.")
        line.quantity = changes["quantity"]
        line.line_total = calculate_line_total(line.quantity, line.unit_cost)

    if "notes" in changes:
        line.notes = changes["notes"]

    po.updated_at = datetime.utcnow()
    recalculate_total(po)
    db.commit()
    return serialize_purchase_order(load_purchase_order(db, po.id))


@router.post("/{po_id}/submit-for-approval", response_model=PurchaseOrderResponse)
def submit_purchase_order_for_approval(po_id: int, db: Session = Depends(get_db)):
    po = load_purchase_order(db, po_id)
    require_draft(po)
    po.status = PENDING_APPROVAL
    po.updated_at = datetime.utcnow()
    db.commit()
    return serialize_purchase_order(load_purchase_order(db, po.id))


@router.post("/{po_id}/approve", response_model=PurchaseOrderResponse)
def approve_purchase_order(
    po_id: int,
    payload: PurchaseOrderApprove | None = None,
    db: Session = Depends(get_db),
):
    po = load_purchase_order(db, po_id)
    if po.status != PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="Only pending approval purchase orders can be approved.")
    if not po.lines:
        raise HTTPException(status_code=400, detail="Cannot approve a purchase order with no lines.")

    now = datetime.utcnow()
    po.status = APPROVED
    po.approved_at = now
    po.updated_at = now
    if payload and payload.approved_by is not None:
        po.approved_by = payload.approved_by
    db.commit()
    return serialize_purchase_order(load_purchase_order(db, po.id))


@router.post("/{po_id}/issue", response_model=PurchaseOrderResponse)
def issue_purchase_order(po_id: int, db: Session = Depends(get_db)):
    po = load_purchase_order(db, po_id)
    if po.status != APPROVED:
        raise HTTPException(status_code=400, detail="Only approved purchase orders can be issued.")

    now = datetime.utcnow()
    po.status = ISSUED
    po.issued_at = now
    po.updated_at = now
    db.commit()
    return serialize_purchase_order(load_purchase_order(db, po.id))


@router.post("/{po_id}/receive", response_model=PurchaseOrderResponse)
def receive_purchase_order(po_id: int, db: Session = Depends(get_db)):
    po = load_purchase_order(db, po_id)
    if po.status != ISSUED:
        raise HTTPException(status_code=400, detail="Only issued purchase orders can be received.")

    now = datetime.utcnow()
    po.status = RECEIVED
    po.received_at = now
    po.updated_at = now
    db.commit()
    return serialize_purchase_order(load_purchase_order(db, po.id))


@router.post("/{po_id}/cancel", response_model=PurchaseOrderResponse)
def cancel_purchase_order(po_id: int, db: Session = Depends(get_db)):
    po = load_purchase_order(db, po_id)
    if po.status not in {DRAFT, PENDING_APPROVAL, APPROVED}:
        raise HTTPException(
            status_code=400,
            detail="Only draft, pending approval, or approved purchase orders can be cancelled.",
        )

    now = datetime.utcnow()
    po.status = CANCELLED
    po.cancelled_at = now
    po.updated_at = now
    db.commit()
    return serialize_purchase_order(load_purchase_order(db, po.id))
