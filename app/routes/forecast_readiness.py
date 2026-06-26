from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.product import Product
from app.services.seasonality_backtesting import (
    audit_product_forecast_inputs,
    forecast_readiness_summary,
    list_forecast_readiness,
)
from app.services.perf_logging import perf_timer


router = APIRouter(tags=["forecast-readiness"])


@router.get("/forecast-readiness/summary")
def get_forecast_readiness_summary(db: Session = Depends(get_db)):
    with perf_timer("forecast_readiness.summary", summary_calculated=True) as perf:
        result = forecast_readiness_summary(db)
        perf["product_count"] = result.get("product_count")
        return result


@router.get("/products/forecast-readiness")
def list_products_forecast_readiness(
    filter: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    with perf_timer(
        "forecast_readiness.products",
        filter=filter,
        search=search,
        limit=limit,
        offset=offset,
        summary_calculated=True,
    ) as perf:
        try:
            rows = list_forecast_readiness(db, filter_name=filter, search=search)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        perf["total"] = len(rows)
        result = rows[offset : offset + limit]
        perf["returned"] = len(result)
        return result


@router.get("/products/{product_id}/forecast-readiness")
def get_product_forecast_readiness(product_id: int, db: Session = Depends(get_db)):
    product = (
        db.query(Product)
        .options(
            selectinload(Product.inventory_positions),
            selectinload(Product.orderpro_order_items),
            selectinload(Product.seasonality_profile),
            selectinload(Product.seasonality_backtests),
            selectinload(Product.supplier_record),
        )
        .filter(Product.id == product_id)
        .first()
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return audit_product_forecast_inputs(db, product)
