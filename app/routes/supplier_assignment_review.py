from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.supplier_assignment_review import (
    build_supplier_assignment_review_report,
    confirm_supplier_assignment,
    filter_review_items,
    reject_supplier_assignment,
    review_item_for_product,
    summarize_review_items,
)
from app.models.product import Product


router = APIRouter(tags=["supplier-assignment-review"])


class SupplierAssignmentConfirmRequest(BaseModel):
    supplier_id: int
    reviewed_by: str | None = None
    note: str | None = None


class SupplierAssignmentRejectRequest(BaseModel):
    reason: str | None = None
    reviewed_by: str | None = None


@router.get("/supplier-assignment-review/summary")
def get_supplier_assignment_review_summary(db: Session = Depends(get_db)):
    plan = build_supplier_assignment_review_report(db)
    return plan.summary


@router.get("/supplier-assignment-review/items")
def list_supplier_assignment_review_items(
    status: str | None = Query(default=None),
    confidence: str | None = Query(default=None),
    suggestion_source: str | None = Query(default=None),
    has_stock: bool | None = Query(default=None),
    has_demand: bool | None = Query(default=None),
    has_open_demand: bool | None = Query(default=None),
    category: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    supplier_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    plan = build_supplier_assignment_review_report(db)
    items = filter_review_items(
        plan.items,
        status=status,
        confidence=confidence,
        suggestion_source=suggestion_source,
        has_stock=has_stock,
        has_demand=has_demand,
        has_open_demand=has_open_demand,
        category=category,
        brand=brand,
        supplier_id=supplier_id,
    )
    return items[offset : offset + limit]


@router.get("/products/{product_id}/supplier-assignment-review")
def get_product_supplier_assignment_review(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    if product.supplier_id is not None:
        return {
            **review_item_for_product(db, product),
            "status": "confirmed",
        }
    if not (
        product.source_system == "orderpro"
        or product.orderpro_id is not None
        or product.orderpro_sku is not None
    ):
        raise HTTPException(status_code=404, detail="Product is not an OrderPro product.")
    return review_item_for_product(db, product)


@router.post("/products/{product_id}/supplier-assignment-review/confirm")
def confirm_product_supplier_assignment(
    product_id: int,
    payload: SupplierAssignmentConfirmRequest,
    db: Session = Depends(get_db),
):
    try:
        review = confirm_supplier_assignment(
            db,
            product_id=product_id,
            supplier_id=payload.supplier_id,
            reviewed_by=payload.reviewed_by,
            note=payload.note,
        )
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=404 if "not found" in detail.lower() else 400, detail=detail) from exc
    return _serialize_review(review)


@router.post("/products/{product_id}/supplier-assignment-review/reject")
def reject_product_supplier_assignment(
    product_id: int,
    payload: SupplierAssignmentRejectRequest | None = None,
    db: Session = Depends(get_db),
):
    payload = payload or SupplierAssignmentRejectRequest()
    try:
        review = reject_supplier_assignment(
            db,
            product_id=product_id,
            reason=payload.reason,
            reviewed_by=payload.reviewed_by,
        )
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=404 if "not found" in detail.lower() else 400, detail=detail) from exc
    return _serialize_review(review)


def _serialize_review(review):
    return {
        "id": review.id,
        "product_id": review.product_id,
        "suggested_supplier_id": review.suggested_supplier_id,
        "suggestion_source": review.suggestion_source,
        "confidence_label": review.confidence_label,
        "confidence_score": review.confidence_score,
        "status": review.status,
        "evidence_summary": review.evidence_summary,
        "warnings": review.warnings or [],
        "reviewed_supplier_id": review.reviewed_supplier_id,
        "reviewed_by": review.reviewed_by,
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        "notes": review.notes,
    }
