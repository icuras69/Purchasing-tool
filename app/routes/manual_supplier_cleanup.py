from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.manual_supplier_cleanup import (
    ManualSupplierCleanupConflict,
    assign_supplier_to_product,
    get_cleanup_candidate,
    get_cleanup_summary,
    list_cleanup_candidates,
    record_cleanup_review,
    search_cleanup_suppliers,
)


router = APIRouter(prefix="/api/manual-supplier-cleanup", tags=["manual-supplier-cleanup"])


class ManualSupplierAssignRequest(BaseModel):
    supplier_id: int
    reviewed_by: str | None = None
    notes: str | None = None


class ManualSupplierReviewRequest(BaseModel):
    status: str
    reviewed_by: str | None = None
    notes: str | None = None


@router.get("/candidates")
def get_manual_supplier_cleanup_candidates(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=250),
    search: str | None = Query(default=None),
    priority_only: bool = Query(default=False),
    sort_by: str = Query(default="priority"),
    sort_direction: str = Query(default="desc"),
    has_open_demand: bool | None = Query(default=None),
    has_stock: bool | None = Query(default=None),
    has_demand_history: bool | None = Query(default=None),
    has_cost: bool | None = Query(default=None),
    has_existing_suggestion: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return list_cleanup_candidates(
        db,
        page=page,
        page_size=page_size,
        search=search,
        priority_only=priority_only,
        sort_by=sort_by,
        sort_direction=sort_direction,
        has_open_demand=has_open_demand,
        has_stock=has_stock,
        has_demand_history=has_demand_history,
        has_cost=has_cost,
        has_existing_suggestion=has_existing_suggestion,
    )


@router.get("/candidates/{product_id}")
def get_manual_supplier_cleanup_candidate(product_id: int, db: Session = Depends(get_db)):
    candidate = get_cleanup_candidate(db, product_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Cleanup candidate not found.")
    return candidate


@router.get("/suppliers")
def get_manual_supplier_cleanup_suppliers(
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return search_cleanup_suppliers(db, search=search, page=page, page_size=page_size)


@router.post("/candidates/{product_id}/assign")
def assign_manual_supplier_cleanup_candidate(
    product_id: int,
    payload: ManualSupplierAssignRequest,
    db: Session = Depends(get_db),
):
    try:
        return assign_supplier_to_product(
            db,
            product_id=product_id,
            supplier_id=payload.supplier_id,
            reviewed_by=payload.reviewed_by,
            notes=payload.notes,
        )
    except ManualSupplierCleanupConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.post("/candidates/{product_id}/review")
def review_manual_supplier_cleanup_candidate(
    product_id: int,
    payload: ManualSupplierReviewRequest,
    db: Session = Depends(get_db),
):
    try:
        return record_cleanup_review(
            db,
            product_id=product_id,
            status=payload.status,
            reviewed_by=payload.reviewed_by,
            notes=payload.notes,
        )
    except ValueError as exc:
        db.rollback()
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except Exception:
        db.rollback()
        raise


@router.get("/summary")
def get_manual_supplier_cleanup_summary(db: Session = Depends(get_db)):
    return get_cleanup_summary(db)
