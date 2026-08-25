from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import traceback

from app.core.config import settings
from app.db.session import get_db
from app.models.inventory_position import InventoryPosition
from app.schemas.inventory import InventoryPositionResponse, InventorySyncResult
from app.services.inventory_sync import sync_inventory_from_provider
from app.services.orderpro_csv_provider import OrderProCsvProvider
from app.services.orderpro_client import OrderProClient, OrderProClientError, OrderProConfigError
from app.services.orderpro_sync_planner import apply_inventory_sync

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.post("/sync/orderpro", response_model=InventorySyncResult)
def sync_orderpro_inventory(db: Session = Depends(get_db)):
    if not settings.orderpro_sync_enabled:
        raise HTTPException(
            status_code=409,
            detail="OrderPro sync is disabled. Set ORDERPRO_SYNC_ENABLED=true before refreshing stock.",
        )

    try:
        client = OrderProClient()
        records = client.get_inventory()
        sync_time = datetime.now(timezone.utc)
        result = apply_inventory_sync(
            db,
            records,
            synced_at=sync_time,
            complete_snapshot=True,
        )
        db.commit()
    except OrderProConfigError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(error)) from error
    except OrderProClientError as error:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(error)) from error
    except Exception as error:
        db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(error).__name__}: {error}") from error

    summary = result["summary"]
    return {
        "source_system": "orderpro",
        "records_received": summary["orderpro_inventory_rows"],
        "records_upserted": (
            summary["inventory_positions_created"]
            + summary["inventory_positions_updated"]
        ),
        "records_skipped": (
            summary["rows_missing_product_match"]
            + summary["rows_missing_warehouse_id"]
        ),
        "message": "OrderPro stock refresh completed. Purchasing AI was updated; OrderPro was not modified.",
        "sync_completed_at": sync_time,
        "complete_snapshot": True,
        "warehouses_created": summary["warehouses_created"],
        "warehouses_updated": summary["warehouses_updated"],
        "inventory_positions_created": summary["inventory_positions_created"],
        "inventory_positions_updated": summary["inventory_positions_updated"],
        "inventory_positions_zeroed": summary["inventory_positions_zeroed"],
        "products_current_stock_updated": summary["products_current_stock_updated"],
        "products_current_stock_zeroed": summary["products_current_stock_zeroed"],
        "rows_missing_product_match": summary["rows_missing_product_match"],
        "rows_missing_warehouse_id": summary["rows_missing_warehouse_id"],
        "unmatched_rows_sample": [
            *result["rows_missing_product_match_sample"],
            *result["rows_missing_warehouse_id_sample"],
        ][:10],
        "warnings": result["warnings"],
    }


@router.post("/sync/orderpro-csv", response_model=InventorySyncResult)
def sync_orderpro_inventory_csv(
    csv_path: str = Query(..., description="Absolute path to the OrderPro inventory CSV"),
    db: Session = Depends(get_db),
):
    try:
        provider = OrderProCsvProvider(csv_path)
        result = sync_inventory_from_provider(db, provider)
        result["message"] = "Inventory sync from OrderPro CSV completed."
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/positions", response_model=list[InventoryPositionResponse])
def list_inventory_positions(db: Session = Depends(get_db)):
    return db.query(InventoryPosition).order_by(InventoryPosition.product_id.asc()).all()
