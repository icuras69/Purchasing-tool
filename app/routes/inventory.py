from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import traceback

from app.db.session import get_db
from app.models.inventory_position import InventoryPosition
from app.schemas.inventory import InventoryPositionResponse, InventorySyncResult
from app.services.inventory_sync import sync_inventory_from_provider
from app.services.orderpro_provider import OrderProProvider
from app.services.orderpro_csv_provider import OrderProCsvProvider

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.post("/sync/orderpro", response_model=InventorySyncResult)
def sync_orderpro_inventory(db: Session = Depends(get_db)):
    try:
        provider = OrderProProvider()
        result = sync_inventory_from_provider(db, provider)
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


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