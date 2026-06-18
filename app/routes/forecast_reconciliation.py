from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.forecast_input_reconciliation import (
    build_readiness_csv,
    get_product_readiness_detail,
    get_readiness_summary,
    list_readiness_candidates,
)


router = APIRouter(prefix="/api/forecast-reconciliation", tags=["forecast-reconciliation"])


@router.get("/summary")
def get_forecast_reconciliation_summary(db: Session = Depends(get_db)):
    return get_readiness_summary(db)


@router.get("/products")
def list_forecast_reconciliation_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=250),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    missing_input: str | None = Query(default=None),
    supplier_id: int | None = Query(default=None),
    has_open_demand: bool | None = Query(default=None),
    has_stock: bool | None = Query(default=None),
    sort_by: str = Query(default="readiness_score"),
    sort_direction: str = Query(default="asc"),
    db: Session = Depends(get_db),
):
    return list_readiness_candidates(
        db,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        missing_input=missing_input,
        supplier_id=supplier_id,
        has_open_demand=has_open_demand,
        has_stock=has_stock,
        sort_by=sort_by,
        sort_direction=sort_direction,
    )


@router.get("/products/{product_id}")
def get_forecast_reconciliation_product(product_id: int, db: Session = Depends(get_db)):
    detail = get_product_readiness_detail(db, product_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return detail


@router.get("/export.csv")
def export_forecast_reconciliation_csv(
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    missing_input: str | None = Query(default=None),
    supplier_id: int | None = Query(default=None),
    has_open_demand: bool | None = Query(default=None),
    has_stock: bool | None = Query(default=None),
    sort_by: str = Query(default="readiness_score"),
    sort_direction: str = Query(default="asc"),
    db: Session = Depends(get_db),
):
    exported = build_readiness_csv(
        db,
        search=search,
        status=status,
        missing_input=missing_input,
        supplier_id=supplier_id,
        has_open_demand=has_open_demand,
        has_stock=has_stock,
        sort_by=sort_by,
        sort_direction=sort_direction,
    )
    return Response(
        content=exported.content,
        media_type=exported.content_type,
        headers={"Content-Disposition": f'attachment; filename="{exported.filename}"'},
    )
