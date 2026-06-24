from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.demand_history_reconciliation import (
    build_demand_coverage_csv,
    get_demand_coverage_detail,
    get_demand_reconciliation_summary,
    list_demand_coverage_products,
)
from app.services.perf_logging import perf_timer


router = APIRouter(prefix="/api/demand-history-reconciliation", tags=["demand-history-reconciliation"])


@router.get("/summary")
def demand_history_summary(db: Session = Depends(get_db)):
    with perf_timer("demand_history.summary", summary_calculated=True) as perf:
        result = get_demand_reconciliation_summary(db)
        perf["product_count"] = result.get("total_products")
        return result


@router.get("/products")
def demand_history_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=250),
    search: str | None = Query(default=None),
    has_history: bool | None = Query(default=None),
    has_recent_demand: bool | None = Query(default=None),
    stale_only: bool | None = Query(default=None),
    supplier_id: int | None = Query(default=None),
    sort_by: str = Query(default="latest_demand_date"),
    sort_direction: str = Query(default="desc"),
    db: Session = Depends(get_db),
):
    with perf_timer(
        "demand_history.products",
        page=page,
        page_size=page_size,
        search=search,
        has_history=has_history,
        has_recent_demand=has_recent_demand,
        stale_only=stale_only,
        supplier_id=supplier_id,
        sort_by=sort_by,
        sort_direction=sort_direction,
        summary_calculated=True,
    ) as perf:
        result = list_demand_coverage_products(
            db,
            page=page,
            page_size=page_size,
            search=search,
            has_history=has_history,
            has_recent_demand=has_recent_demand,
            stale_only=stale_only,
            supplier_id=supplier_id,
            sort_by=sort_by,
            sort_direction=sort_direction,
        )
        perf["total"] = result.get("total")
        perf["returned"] = len(result.get("items", []))
        return result


@router.get("/products/{product_id}")
def demand_history_product_detail(product_id: int, db: Session = Depends(get_db)):
    detail = get_demand_coverage_detail(db, product_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return detail


@router.get("/export.csv")
def demand_history_export_csv(
    search: str | None = Query(default=None),
    has_history: bool | None = Query(default=None),
    has_recent_demand: bool | None = Query(default=None),
    stale_only: bool | None = Query(default=None),
    supplier_id: int | None = Query(default=None),
    sort_by: str = Query(default="latest_demand_date"),
    sort_direction: str = Query(default="desc"),
    db: Session = Depends(get_db),
):
    exported = build_demand_coverage_csv(
        db,
        search=search,
        has_history=has_history,
        has_recent_demand=has_recent_demand,
        stale_only=stale_only,
        supplier_id=supplier_id,
        sort_by=sort_by,
        sort_direction=sort_direction,
    )
    return Response(
        content=exported.content,
        media_type=exported.content_type,
        headers={"Content-Disposition": f'attachment; filename="{exported.filename}"'},
    )
